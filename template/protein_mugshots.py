#!/usr/bin/env python3
"""Render three-view pLDDT mugshots for completed ProteinFold runs."""

import argparse
import base64
import csv
import html
import os
import shutil
import signal
import subprocess
import sys
import urllib.parse

TOP_RANKED_DIR = "top_ranked_structures"
STRUCTURE_SUFFIXES = (".pdb", ".cif", ".mmcif")
PNG_SUFFIX = "_plddt_mugshot.png"
MUGSHOT_DIR = "mugshots"
MANIFEST = "mugshot_manifest.tsv"
INDEX = "mugshot_index.html"
BATCH_SCRIPT = "mugshot_batch.pml"

DEFAULT_IMAGE = (
    "/srv/scratch/sbf-pipelines/containers/"
    "jysgro-pymol-3.1.0-amd64-ab2facf7869c.sif"
)
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 400
DEFAULT_TIMEOUT = 3600
DEFAULT_THREADS = 2
WEBP_QUALITY = 90

BANDS = (
    ("af_plddt_very_high", (0.0000, 0.3255, 0.8392), "b > 89.9999"),
    ("af_plddt_high", (0.3961, 0.7961, 0.9529), "b > 69.9999 and b < 90"),
    ("af_plddt_low", (1.0000, 0.8588, 0.0745), "b > 49.9999 and b < 70"),
    ("af_plddt_very_low", (1.0000, 0.4902, 0.2706), "b < 50"),
)

MANIFEST_FIELDS = (
    "source_path",
    "output_png",
    "method",
    "status",
    "skip_reason",
    "confidence_source",
    "validation",
    "error",
    "renderer",
    "renderer_version",
    "elapsed_seconds",
    "png_bytes",
)

RESULT = "MUGSHOT_RESULT"
VERSION = "MUGSHOT_RENDERER_VERSION"
COMPLETE = "MUGSHOT_BATCH_COMPLETE"


def log(message):
    print("[mugshots] %s" % message, flush=True)


def debug(message):
    print("[mugshots] %s" % message, file=sys.stderr, flush=True)


def valid_png(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def valid_webp(path):
    try:
        with open(path, "rb") as handle:
            header = handle.read(12)
        return header[:4] == b"RIFF" and header[8:] == b"WEBP"
    except OSError:
        return False


def discover(out_dir):
    candidates = []
    for root, dirs, files in os.walk(os.path.abspath(out_dir)):
        if os.path.basename(root) != TOP_RANKED_DIR:
            continue
        dirs[:] = []
        relative = os.path.relpath(root, out_dir).split(os.sep)
        method = relative[0].lower() if relative else "unknown"
        for name in sorted(files):
            suffix = os.path.splitext(name)[1].lower()
            path = os.path.join(root, name)
            if suffix in STRUCTURE_SUFFIXES and os.path.isfile(path):
                candidates.append(
                    {
                        "path": path,
                        "relative": os.path.relpath(path, out_dir),
                        "method": method,
                        "stem": os.path.splitext(name)[0],
                        "suffix": suffix,
                    }
                )
    return sorted(candidates, key=lambda item: item["relative"])


def plan(candidates):
    counts = {}
    for candidate in candidates:
        key = (os.path.dirname(candidate["path"]), candidate["stem"])
        counts[key] = counts.get(key, 0) + 1
    claimed = set()
    tasks = []
    for candidate in candidates:
        stem = candidate["stem"]
        key = (os.path.dirname(candidate["path"]), stem)
        if counts[key] > 1:
            stem += "_" + candidate["suffix"].lstrip(".")
        target = os.path.join(os.path.dirname(candidate["path"]), stem + PNG_SUFFIX)
        sequence = 2
        while target in claimed:
            target = os.path.join(
                os.path.dirname(candidate["path"]), "%s_%d%s" % (stem, sequence, PNG_SUFFIX)
            )
            sequence += 1
        claimed.add(target)
        task = {
            "candidate": candidate,
            "target": target,
            "confidence_source": "pdb.B-factor" if candidate["suffix"] == ".pdb" else "mmcif.B_iso_or_equiv",
            "validation": "pending",
            "status": "pending",
            "skip_reason": "",
            "error": "",
            "elapsed": "",
            "png_bytes": "",
            "panels": (),
            "render_path": "",
            "preview": "",
        }
        if valid_png(target):
            task["status"] = "skipped"
            task["validation"] = "existing_png"
            task["skip_reason"] = "already_rendered"
            task["png_bytes"] = str(os.path.getsize(target))
        tasks.append(task)
    return tasks


def pymol_script(tasks, width, height, threads):
    jobs = [
        (
            task["candidate"]["path"],
            task["render_path"],
            "pdb" if task["candidate"]["suffix"] == ".pdb" else "cif",
        )
        for task in tasks
        if task["status"] == "pending"
    ]
    lines = [
        "python",
        "import math, os, sys, time",
        "from pymol import cmd",
        "class ConfidenceError(Exception): pass",
        "BANDS = %r" % (BANDS,),
        "JOBS = %r" % (jobs,),
        "rendered = 0",
        "for source, destination, file_format in JOBS:",
        "    started = time.time()",
        "    status, detail = 'rendered', ''",
        "    try:",
        "        cmd.reinitialize()",
        "        cmd.set('max_threads', %d)" % threads,
        "        cmd.set('ray_shadows', 0)",
        "        cmd.set('orthoscopic', 1)",
        "        cmd.bg_color('white')",
        "        cmd.set('ray_opaque_background', 1)",
        "        cmd.viewport(%d, %d)" % (max(64, width // 3), height),
        "        cmd.load(source, 'mugshot', format=file_format)",
        "        if 'mugshot' not in cmd.get_names('objects'):",
        "            raise RuntimeError('PyMOL could not load the structure')",
        "        scores = []",
        "        cmd.iterate('mugshot', 'scores.append(b)', space={'scores': scores})",
        "        if not scores:",
        "            raise ConfidenceError('no atom records')",
        "        if any(not math.isfinite(value) for value in scores):",
        "            raise ConfidenceError('non-finite confidence value')",
        "        low, high = min(scores), max(scores)",
        "        detail = '%d atom record(s), pLDDT range %.2f..%.2f' % (len(scores), low, high)",
        "        if low < -0.011 or high > 100.011:",
        "            raise ConfidenceError('confidence outside 0..100; ' + detail)",
        "        if high - low < 0.01:",
        "            raise ConfidenceError('constant confidence values; ' + detail)",
        "        if high <= 1.011:",
        "            raise ConfidenceError('apparent 0..1 confidence scale; ' + detail)",
        "        cmd.hide('everything', 'mugshot')",
        "        cmd.show('cartoon', 'mugshot')",
        "        for colour, rgb, selector in BANDS:",
        "            cmd.set_color(colour, list(rgb))",
        "            cmd.color(colour, 'mugshot and ' + selector)",
        "        cmd.orient('mugshot')",
        "        cmd.zoom('mugshot', complete=1)",
        "        base_view = cmd.get_view()",
        "        for view, axis in (('front', None), ('side', 'y'), ('top', 'x')):",
        "            cmd.set_view(base_view)",
        "            if axis: cmd.turn(axis, 90)",
        "            cmd.ray()",
        "            cmd.png(destination + '.' + view + '.png')",
        "        panels = [destination + '.' + view + '.png' for view in ('front', 'side', 'top')]",
        "        if not all(os.path.isfile(path) and os.path.getsize(path) for path in panels):",
        "            raise RuntimeError('PyMOL wrote an empty view panel')",
        "        rendered += 1",
        "    except ConfidenceError as error:",
        "        status, detail = 'invalid_confidence', str(error)",
        "    except Exception as error:",
        "        status, detail = 'error', str(error).replace('\\t', ' ').replace('\\n', ' ')",
        "    sys.__stdout__.write('%s\\t%%s\\t%%s\\t%%s\\t%%.3f\\n' %% (status, destination, detail, time.time() - started))" % RESULT,
        "    sys.__stdout__.flush()",
        "sys.__stdout__.write('%s\\t%%s\\n' %% cmd.get_version()[0])" % VERSION,
        "sys.__stdout__.write('%s\\t%%d\\t%%d\\n' %% (rendered, len(JOBS)))" % COMPLETE,
        "sys.__stdout__.flush()",
        "python end",
    ]
    return "\n".join(lines) + "\n"


def renderer_command(image, threads, script_path, out_dir):
    apptainer = shutil.which("apptainer")
    if not apptainer:
        raise RuntimeError("Apptainer executable not found")
    if not os.path.isfile(image) or not os.access(image, os.R_OK):
        raise RuntimeError("renderer image is unavailable: %s" % image)
    real_out = os.path.realpath(out_dir)
    command = [
        apptainer, "exec", "--cleanenv", "--bind", "%s:%s" % (real_out, real_out),
        "--env", "HOME=%s" % os.path.dirname(script_path),
    ]
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        command.extend(["--env", "%s=%d" % (name, threads)])
    command.extend([image, "pymol", "-cq", script_path])
    return command


def fail(task, reason, detail=""):
    task["status"] = "failed"
    if task["validation"] == "pending":
        task["validation"] = "not_validated"
    task["error"] = (reason + (": " + detail if detail else ""))[:500]


def compose(tasks, manifest_dir, timeout):
    jobs = [
        task
        for task in tasks
        if task["panels"]
        or (task["status"] in ("rendered", "skipped") and valid_png(task["target"]))
    ]
    if not jobs:
        return
    converter = shutil.which("convert")
    if not converter:
        for task in jobs:
            if task["panels"]:
                fail(task, "compositor_unavailable", "ImageMagick convert not found")
        cleanup(tasks)
        return
    command = [converter]
    for index, task in enumerate(jobs):
        task["preview"] = os.path.join(manifest_dir, ".preview-%06d.webp" % index)
        command.append("(")
        if task["panels"]:
            for label, panel in zip(("FRONT", "SIDE", "TOP"), task["panels"]):
                command.extend(
                    [
                        "(", panel, "-gravity", "NorthWest", "-fill", "black",
                        "-undercolor", "white", "-pointsize", "12",
                        "-annotate", "+8+8", label, ")",
                    ]
                )
            command.extend(["+append", "-write", task["render_path"]])
        else:
            command.append(task["target"])
        command.extend(
            ["-quality", str(WEBP_QUALITY), "-write", task["preview"], "+delete", ")"]
        )
    command.extend(["xc:none", "null:"])
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        stderr = result.stderr.decode("utf-8", "replace").strip()[-400:]
        for task in jobs:
            if task["panels"]:
                if not valid_png(task["render_path"]):
                    fail(task, "compositor_failed", stderr or "no valid composite PNG")
                    continue
                try:
                    os.replace(task["render_path"], task["target"])
                    task["status"] = "rendered"
                    task["png_bytes"] = str(os.path.getsize(task["target"]))
                except OSError as error:
                    fail(task, "replace_failed", str(error))
            if not valid_webp(task["preview"]):
                task["preview"] = ""
    except subprocess.TimeoutExpired:
        for task in jobs:
            if task["panels"]:
                fail(task, "compositor_timeout", "timed out after %ds" % timeout)
    except OSError as error:
        for task in jobs:
            if task["panels"]:
                fail(task, "compositor_failed", str(error))
    finally:
        cleanup(tasks)


def cleanup(tasks):
    for task in tasks:
        for path in task["panels"]:
            try:
                os.unlink(path)
            except OSError:
                pass
        temporary = task["render_path"]
        if temporary and temporary != task["target"]:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def render(image, threads, tasks, out_dir, manifest_dir):
    pending = [task for task in tasks if task["status"] == "pending"]
    if not pending:
        return ""
    for index, task in enumerate(pending):
        task["render_path"] = "%s.mugshot-tmp-%d-%d.png" % (
            task["target"], os.getpid(), index
        )
    script_path = os.path.join(manifest_dir, BATCH_SCRIPT)
    with open(script_path, "w") as handle:
        handle.write(pymol_script(tasks, DEFAULT_WIDTH, DEFAULT_HEIGHT, threads))
    try:
        command = renderer_command(image, threads, script_path, out_dir)
    except RuntimeError as error:
        for task in pending:
            fail(task, "renderer_unavailable", str(error))
        return ""

    log("Generating pLDDT previews for %d structures..." % len(pending))
    process = None
    stdout = stderr = b""
    timed_out = False
    try:
        # Isolate Apptainer and PyMOL so the renderer timeout stops both.
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
        )
        stdout, stderr = process.communicate(timeout=DEFAULT_TIMEOUT)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        stdout, stderr = process.communicate()
    except OSError as error:
        for task in pending:
            fail(task, "renderer_failed", str(error))
        return ""

    results = {}
    version = ""
    completed = False
    for line in stdout.decode("utf-8", "replace").splitlines():
        fields = line.split("\t")
        if len(fields) >= 5 and fields[0] == RESULT:
            results[fields[2]] = (fields[1], fields[3], fields[4])
        elif len(fields) >= 2 and fields[0] == VERSION:
            version = fields[1]
        elif fields and fields[0] == COMPLETE:
            completed = True
    process_error = ""
    if timed_out:
        process_error = "timed out after %ds" % DEFAULT_TIMEOUT
    elif process.returncode:
        process_error = "exited with status %d" % process.returncode
    stderr_tail = " | ".join(stderr.decode("utf-8", "replace").strip().splitlines()[-3:])
    if stderr_tail:
        process_error += ("; " if process_error else "") + stderr_tail

    for task in pending:
        outcome = results.get(task["render_path"])
        panels = tuple(task["render_path"] + "." + view + ".png" for view in ("front", "side", "top"))
        panels_ready = all(os.path.isfile(path) and os.path.getsize(path) > 0 for path in panels)
        if outcome and outcome[0] == "rendered" and panels_ready:
            task["panels"] = panels
            task["validation"] = "valid"
            task["elapsed"] = outcome[2]
        else:
            status = outcome[0] if outcome else ""
            detail = outcome[1] if outcome else process_error or "no renderer result"
            task["validation"] = "invalid_confidence" if status == "invalid_confidence" else "not_validated"
            reason = "invalid_confidence" if status == "invalid_confidence" else (
                "renderer_timeout" if timed_out else "renderer_failed"
            )
            fail(task, reason, detail)
            for panel in panels:
                try:
                    os.unlink(panel)
                except OSError:
                    pass
    compose(tasks, manifest_dir, DEFAULT_TIMEOUT)
    if not completed and not timed_out:
        debug("WARNING: renderer did not report batch completion")
    if version:
        debug("Renderer version: PyMOL %s" % version)
    return version


def write_manifest(directory, tasks, renderer, version):
    path = os.path.join(directory, MANIFEST)
    temporary = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(temporary, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            for task in tasks:
                candidate = task["candidate"]
                writer.writerow(
                    {
                        "source_path": candidate["path"],
                        "output_png": task["target"],
                        "method": candidate["method"],
                        "status": task["status"],
                        "skip_reason": task["skip_reason"],
                        "confidence_source": task["confidence_source"],
                        "validation": task["validation"],
                        "error": task["error"].replace("\t", " ").replace("\n", " "),
                        "renderer": renderer,
                        "renderer_version": version,
                        "elapsed_seconds": task["elapsed"],
                        "png_bytes": task["png_bytes"],
                    }
                )
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
    return path


def write_index(directory, tasks):
    counts = {}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    summary = ", ".join("%s=%d" % item for item in sorted(counts.items())) or "none"
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>ProteinFold pLDDT mugshots</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:1rem;background:#eee;color:#222}.card{background:#fff;margin:0 0 .75rem;padding:.5rem;border:1px solid #bbb;border-radius:6px}.card h2{font-size:1rem;margin:.1rem 0 .4rem}.card img{display:block;width:100%;max-width:1200px;height:auto}.meta{font-family:monospace;font-size:.8rem;margin-top:.35rem;color:#555;overflow-wrap:anywhere}.legend{display:flex;gap:.6rem 1.1rem;align-items:center;flex-wrap:wrap;background:#fff;border:1px solid #bbb;border-radius:6px;padding:.65rem .8rem;margin:.5rem 0 1rem;width:fit-content}.band{display:flex;gap:.4rem;align-items:center}.swatch{width:2rem;height:1rem;border:1px solid #777}.bad{color:#a00}</style></head><body>",
        "<h1>ProteinFold pLDDT mugshots</h1><p>Front, side, and top views. Outcomes: %s.</p>" % html.escape(summary),
        "<div class='legend'><strong>pLDDT confidence</strong><span class='band'><i class='swatch' style='background:#0053D6'></i>&ge;90 very high</span><span class='band'><i class='swatch' style='background:#65CBF3'></i>70&ndash;&lt;90 confident</span><span class='band'><i class='swatch' style='background:#FFDB13'></i>50&ndash;&lt;70 low</span><span class='band'><i class='swatch' style='background:#FF7D45'></i>&lt;50 very low</span></div>",
    ]
    temporary = ""
    try:
        for task in tasks:
            candidate = task["candidate"]
            preview_valid = valid_webp(task["preview"])
            image_path = task["preview"] if preview_valid else task["target"]
            mime = "image/webp" if preview_valid else "image/png"
            image_valid = preview_valid or valid_png(image_path)
            if task["status"] in ("rendered", "skipped") and image_valid:
                with open(image_path, "rb") as handle:
                    image = "<img loading='lazy' src='data:%s;base64,%s' alt='%s'>" % (
                        mime,
                        base64.b64encode(handle.read()).decode("ascii"),
                        html.escape(candidate["stem"], quote=True),
                    )
            else:
                image = "<p class='bad'>%s</p>" % html.escape(task["error"] or task["skip_reason"])
            source = urllib.parse.quote(os.path.relpath(candidate["path"], directory))
            parts.append(
                "<section class='card'><h2>%s</h2>%s<div class='meta'>%s · %s · <a href='%s'>source</a></div></section>"
                % (
                    html.escape(candidate["relative"]), image,
                    html.escape(candidate["method"]), html.escape(task["status"]), source,
                )
            )
        parts.append("</body></html>")
        path = os.path.join(directory, INDEX)
        temporary = "%s.tmp-%d" % (path, os.getpid())
        with open(temporary, "w") as handle:
            handle.write("\n".join(parts) + "\n")
        os.replace(temporary, path)
        return path
    finally:
        for task in tasks:
            try:
                os.unlink(task["preview"])
            except OSError:
                pass
        try:
            os.unlink(temporary)
        except OSError:
            pass


def run(args):
    out_dir = os.path.realpath(os.path.abspath(args.out_dir))
    manifest_dir = os.path.join(out_dir, MUGSHOT_DIR)
    os.makedirs(manifest_dir, exist_ok=True)
    image = os.environ.get("MUGSHOT_RENDERER_IMAGE", DEFAULT_IMAGE)
    try:
        threads = max(1, int(os.environ.get("PBS_NCPUS", DEFAULT_THREADS)))
    except ValueError:
        threads = DEFAULT_THREADS
    tasks = plan(discover(out_dir))
    pending = sum(task["status"] == "pending" for task in tasks)
    skipped = sum(task["status"] == "skipped" for task in tasks)
    existing_index = os.path.join(manifest_dir, INDEX)
    reuse_index = bool(tasks) and skipped == len(tasks) and os.path.isfile(existing_index) and os.path.getsize(existing_index) > 0
    debug("Discovered %d structure(s): %d to render, %d already rendered." % (len(tasks), pending, skipped))
    renderer = "apptainer:%s" % os.path.basename(image)
    version = ""
    try:
        version = render(image, threads, tasks, out_dir, manifest_dir)
    except Exception as error:
        debug("WARNING: mugshot processing failed (%s); ProteinFold results are unaffected." % error)
        for task in tasks:
            if task["status"] == "pending":
                fail(task, "driver_failed", str(error))
    manifest = write_manifest(manifest_dir, tasks, renderer, version)
    index = existing_index if reuse_index else write_index(manifest_dir, tasks)
    rendered = sum(task["status"] == "rendered" for task in tasks)
    skipped = sum(task["status"] == "skipped" for task in tasks)
    failed = sum(task["status"] == "failed" for task in tasks)
    log("pLDDT previews complete: %d created, %d reused, %d failed." % (rendered, skipped, failed))
    for task in tasks:
        if task["status"] == "failed":
            debug("FAILED %s: %s" % (task["candidate"]["relative"], task["error"]))
    debug("Manifest: %s" % manifest)
    debug("Index: %s" % index)
    return 0


def parser():
    result = argparse.ArgumentParser(description="Render pLDDT mugshots for top-ranked structures.")
    result.add_argument("--out-dir", required=True)
    return result


def main(argv=None):
    try:
        return run(parser().parse_args(argv))
    except Exception as error:
        debug("WARNING: unexpected mugshot failure (%s); continuing." % error)
        log("pLDDT previews unavailable; ProteinFold results are unaffected.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
