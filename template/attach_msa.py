#!/usr/bin/env python3
import argparse
import csv
import os
from pathlib import Path
import shutil


def attach_msa(samplesheet, output, source, mode, msa_input, staged_names=None):
    with open(samplesheet, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if "fasta" not in fields:
            raise ValueError("Samplesheet has no fasta column")
        rows = list(reader)

    if not rows:
        raise ValueError("Samplesheet has no samples")

    supplied = Path(msa_input).expanduser().resolve() if msa_input else None
    if supplied and supplied.is_file() and supplied.suffix.lower() != ".a3m":
        raise ValueError("Supplied MSA must be an .a3m file")
    if supplied and not supplied.exists():
        raise ValueError(f"MSA path does not exist: {supplied}")
    if supplied and supplied.is_file() and len(rows) != 1:
        raise ValueError("A single A3M file can only be used with one sample; provide a directory or per-row msa paths")

    source_path = Path(source).expanduser().resolve() if mode != "MANUAL_INPUT" else None
    originals = {}
    if mode == "SAMPLESHEET_INPUT":
        with open(source_path, newline="", encoding="utf-8-sig") as handle:
            for index, row in enumerate(csv.DictReader(handle), start=2):
                originals[index] = (source_path.parent / row["fasta"]).resolve()

    names = {}
    if mode == "DIRECTORY" and staged_names and Path(staged_names).is_file():
        entries = Path(staged_names).read_bytes().split(b"\0")
        if entries[-1] != b"":
            raise ValueError("Invalid staged input mapping")
        names = {os.fsdecode(entries[index]): os.fsdecode(entries[index + 1]) for index in range(0, len(entries) - 1, 2)}

    def usable_path(path, index):
        path = path.resolve()
        if any(character.isspace() for character in str(path)):
            destination = Path(output).parent / "msa_inputs" / f"{index}.a3m"
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, destination)
            return destination
        return path

    for index, row in enumerate(rows, start=1):
        existing = (row.get("msa") or "").strip()
        if existing:
            path = Path(existing)
            if not path.is_absolute():
                path = (source_path.parent if mode == "SAMPLESHEET_INPUT" else Path(samplesheet).parent) / path
            path = path.resolve()
            if not path.is_file():
                raise ValueError(f"MSA file does not exist: {path}")
            row["msa"] = str(usable_path(path, index))
            continue

        fasta = Path(row["fasta"])
        if mode == "SAMPLESHEET_INPUT":
            prefix, separator, filename = fasta.name.partition("_")
            candidate = originals.get(int(prefix)) if separator and prefix.isdigit() else None
            original = candidate if candidate and candidate.name == filename else (source_path.parent / fasta).resolve()
        elif mode == "FASTA_INPUT":
            original = source_path
        elif mode == "DIRECTORY":
            original = source_path / names.get(fasta.name, fasta.name)
        else:
            original = fasta
        stem = original.stem
        directory = supplied if supplied and supplied.is_dir() else original.parent
        match = directory / f"{stem}.a3m"
        if supplied and supplied.is_file():
            match = supplied
        if match.is_file():
            row["msa"] = str(usable_path(match, index))

    if "msa" not in fields:
        fields.append("msa")
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("samplesheet")
    parser.add_argument("output")
    parser.add_argument("source")
    parser.add_argument("mode")
    parser.add_argument("msa_input")
    parser.add_argument("staged_names")
    options = parser.parse_args()
    try:
        attach_msa(options.samplesheet, options.output, options.source, options.mode, options.msa_input, options.staged_names)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"ERROR: Unable to attach ColabFold MSAs: {error}\n")
