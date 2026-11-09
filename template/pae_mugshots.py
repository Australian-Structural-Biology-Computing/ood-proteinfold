#!/usr/bin/env python3
"""Render predicted aligned error (PAE) plots for top-ranked ProteinFold structures.

ProteinFold publishes each model's PAE matrix as ``<id>_<rank>_pae.tsv`` inside
``<method>/<id>/paes/`` (AlphaFold2 adds a mode directory above ``<id>``). The
lowest-numbered file is the top-ranked model, which is the structure copied to
``top_ranked_structures/<id>.<ext>``. Rendering uses only the standard library
so it works on hosts without numpy or matplotlib.
"""

import argparse
import math
import os
import re
import struct
import sys
import zlib

TOP_RANKED_DIR = "top_ranked_structures"
PAES_DIR = "paes"
PAE_SUFFIX = "_pae.png"
PAE_FILE = re.compile(r"^(?P<id>.+)_(?P<rank>\d+)_pae\.tsv$")
PLOT_SIZE = 400
PAE_MAX = 30.0

# Matplotlib "Greens_r" stops, the colouring used by the AlphaFold database.
STOPS = (
    (0, 68, 27),
    (0, 109, 44),
    (35, 139, 69),
    (65, 171, 93),
    (116, 196, 118),
    (161, 217, 155),
    (199, 233, 192),
    (229, 245, 224),
    (247, 252, 245),
)

CSS_GRADIENT = "linear-gradient(to right,%s)" % ",".join("#%02X%02X%02X" % stop for stop in STOPS)


def valid_png(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def find_pae(structure_path):
    """Return the top-ranked PAE TSV for a top_ranked_structures entry, or ''."""
    stem = os.path.splitext(os.path.basename(structure_path))[0]
    directory = os.path.join(os.path.dirname(os.path.dirname(structure_path)), stem, PAES_DIR)
    try:
        names = os.listdir(directory)
    except OSError:
        return ""
    ranked = []
    for name in names:
        match = PAE_FILE.match(name)
        if match and match.group("id") == stem:
            ranked.append((int(match.group("rank")), name))
    return os.path.join(directory, min(ranked)[1]) if ranked else ""


def colour(value):
    position = min(max(value / PAE_MAX, 0.0), 1.0) * (len(STOPS) - 1)
    low = min(int(position), len(STOPS) - 2)
    fraction = position - low
    return tuple(
        int(round(STOPS[low][channel] + (STOPS[low + 1][channel] - STOPS[low][channel]) * fraction))
        for channel in range(3)
    )


def read_matrix(path, size=PLOT_SIZE):
    """Read a square PAE TSV, box-averaging it down to at most size x size."""
    with open(path, "r") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    count = len(lines)
    if count == 0:
        raise ValueError("empty PAE file")
    side = min(size, count)
    spans = [(cell * count // side, (cell + 1) * count // side) for cell in range(side)]
    rows = []
    sums = [0.0] * count
    band = 0
    for index, line in enumerate(lines):
        values = [float(item) for item in line.split("\t")]
        if len(values) != count:
            raise ValueError("PAE matrix is not square (%d rows, %d columns)" % (count, len(values)))
        if not all(math.isfinite(item) for item in values):
            raise ValueError("PAE matrix contains non-finite values")
        for column, item in enumerate(values):
            sums[column] += item
        start, stop = spans[band]
        if index + 1 == stop:
            depth = stop - start
            rows.append([sum(sums[a:b]) / ((b - a) * depth) for a, b in spans])
            sums = [0.0] * count
            band += 1
    return rows


def upscale(rows, size):
    count = len(rows)
    if count >= size:
        return rows
    source = [cell * count // size for cell in range(size)]
    return [[rows[row][column] for column in source] for row in source]


def png_chunk(kind, payload):
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def write_png(path, rows):
    palette = {}
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for value in row:
            key = round(value * 4)
            rgb = palette.get(key)
            if rgb is None:
                rgb = palette[key] = bytes(colour(key / 4.0))
            raw.extend(rgb)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", len(rows[0]), len(rows), 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + png_chunk(b"IEND", b"")
    )
    temporary = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(temporary, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def render_pae(structure_path):
    """Create the PAE plot beside a structure.

    Returns (status, png_path, source_tsv, detail). Status is rendered,
    skipped (up-to-date plot reused), missing (no usable PAE file) or failed.
    """
    stem = os.path.splitext(os.path.basename(structure_path))[0]
    target = os.path.join(os.path.dirname(structure_path), stem + PAE_SUFFIX)
    source = find_pae(structure_path)
    if not source:
        return "missing", "", "", "no PAE file found"
    try:
        if os.path.getsize(source) == 0:
            return "missing", "", source, "PAE file is empty"
        if valid_png(target) and os.path.getmtime(target) >= os.path.getmtime(source):
            return "skipped", target, source, ""
        write_png(target, upscale(read_matrix(source), PLOT_SIZE))
        return "rendered", target, source, ""
    except (OSError, ValueError) as error:
        return "failed", "", source, str(error)[:500]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render PAE plots for top-ranked structures.")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    for root, dirs, files in os.walk(os.path.abspath(args.out_dir)):
        if os.path.basename(root) != TOP_RANKED_DIR:
            continue
        dirs[:] = []
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() in (".pdb", ".cif", ".mmcif"):
                path = os.path.join(root, name)
                status, png, _, detail = render_pae(path)
                print("[pae] %s: %s %s" % (path, status, png or detail), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
