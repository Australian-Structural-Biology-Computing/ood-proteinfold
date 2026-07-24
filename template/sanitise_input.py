#!/usr/bin/env python3
"""Validate and normalise FASTA inputs staged for proteinfold."""

import csv
import hashlib
import os
import shutil
import sys
import tempfile


FASTA_SUFFIXES = (".fa", ".fasta")
YAML_SUFFIXES = (".yaml", ".yml")


def strip_whitespace(value):
    return "".join(
        char for char in value if not char.isspace() and char not in {"\ufeff", "\u200b"}
    )


def sanitise_fasta(source_path, destination_path):
    has_record = False
    record_has_content = False
    blank_lines = 0
    normalised_headers = 0
    normalised_sequence_lines = 0
    normalised_line_endings = 0
    removed_sequence_whitespace = 0
    digest = hashlib.sha256()

    with open(source_path, encoding="utf-8-sig", newline="") as source, open(
        destination_path, "w", encoding="utf-8"
    ) as destination:

        def write(value):
            destination.write(value)
            digest.update(value.encode("utf-8"))

        for line_number, raw_line in enumerate(source, start=1):
            if raw_line.endswith("\r\n") or raw_line.endswith("\r"):
                normalised_line_endings += 1
            line = raw_line.strip()
            if not line:
                blank_lines += 1
                continue
            if line.startswith(">"):
                if has_record and not record_has_content:
                    raise ValueError(
                        f"FASTA record before line {line_number} has no sequence/content"
                    )
                header = line[1:].strip()
                if not header:
                    raise ValueError(f"FASTA header on line {line_number} is empty")
                normalised_header = f">{header}\n"
                if raw_line != normalised_header:
                    normalised_headers += 1
                write(normalised_header)
                has_record = True
                record_has_content = False
                continue
            if not has_record:
                raise ValueError(
                    f"Sequence/content found before the first FASTA header on line {line_number}"
                )
            sequence = strip_whitespace(raw_line)
            if sequence:
                normalised_sequence = f"{sequence}\n"
                if raw_line != normalised_sequence:
                    normalised_sequence_lines += 1
                    removed_sequence_whitespace += len(raw_line.rstrip("\r\n")) - len(sequence)
                write(normalised_sequence)
                record_has_content = True

    if not has_record:
        raise ValueError("No FASTA header found")
    if not record_has_content:
        raise ValueError("Final FASTA record has no sequence/content")

    changes = []
    if blank_lines:
        changes.append(f"removed {blank_lines} blank line(s)")
    if normalised_line_endings:
        changes.append(f"normalised line endings in {normalised_line_endings} line(s)")
    if normalised_headers:
        changes.append(f"normalised {normalised_headers} FASTA header(s)")
    if normalised_sequence_lines:
        changes.append(f"normalised {normalised_sequence_lines} sequence line(s)")
    if removed_sequence_whitespace:
        changes.append(
            f"removed {removed_sequence_whitespace} whitespace character(s) from sequence data"
        )
    return digest.hexdigest(), changes


def sanitise_in_place(path):
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), delete=False) as temporary:
        temporary_path = temporary.name
    try:
        normalised_hash, changes = sanitise_fasta(path, temporary_path)
        os.replace(temporary_path, path)
        return normalised_hash, changes
    except BaseException:
        os.unlink(temporary_path)
        raise


def write_warnings(warning_path, warnings):
    if not warnings:
        return
    with open(warning_path, "w", encoding="utf-8") as handle:
        handle.write("WARNING: Input entries were adjusted before running proteinfold.\n\n")
        handle.write("\n".join(warnings) + "\n")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def input_kind(path):
    suffix = os.path.splitext(path)[1].lower()
    if suffix in FASTA_SUFFIXES:
        return "fasta"
    if suffix in YAML_SUFFIXES:
        return "yaml"
    return None


def unique_sample_id(sample_id, used_ids):
    unique_id = sample_id
    duplicate_number = 2
    while unique_id in used_ids:
        unique_id = f"{sample_id}-{duplicate_number}"
        duplicate_number += 1
    used_ids.add(unique_id)
    return unique_id


def sanitise_samplesheet(samplesheet_path, output_path, input_dir, warning_path, af_method):
    os.makedirs(input_dir, exist_ok=True)
    samplesheet_dir = os.path.dirname(os.path.abspath(samplesheet_path))
    with open(samplesheet_path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if [name.strip() for name in fieldnames[:2]] != ["id", "fasta"]:
            raise ValueError("Samplesheet must start with the required columns: id,fasta")

        id_column, fasta_column = fieldnames[:2]
        rows = []
        seen_paths = {}
        seen_normalised_hashes = {}
        used_ids = set()
        warnings = []

        for index, row in enumerate(reader, start=2):
            if all((value or "").strip() == "" for value in row.values()):
                continue

            input_path = (row.get(fasta_column) or "").strip()
            if not input_path:
                raise ValueError(f"Samplesheet row {index} is missing an input path")
            if not os.path.isabs(input_path):
                input_path = os.path.normpath(os.path.join(samplesheet_dir, input_path))
            if not os.path.isfile(input_path):
                raise ValueError(f"Samplesheet row {index} input file not found: {input_path}")

            kind = input_kind(input_path)
            if kind is None:
                raise ValueError(
                    f"Samplesheet row {index} has unsupported input type: {input_path}. "
                    "Expected a .fa or .fasta file, or a .yaml/.yml file for Boltz."
                )
            if kind == "yaml" and af_method != "boltz":
                raise ValueError(
                    f"Samplesheet row {index} uses YAML input, which is only supported by Boltz"
                )

            source_path = os.path.realpath(input_path)
            if source_path in seen_paths:
                warnings.append(
                    f"Skipped samplesheet row {index}: input path resolves to the same file as "
                    f"row {seen_paths[source_path]}: {source_path}"
                )
                continue
            seen_paths[source_path] = index

            staged_path = os.path.join(input_dir, f"{index}_{os.path.basename(input_path)}")
            if kind == "fasta":
                try:
                    normalised_hash, changes = sanitise_fasta(input_path, staged_path)
                except (OSError, UnicodeError, ValueError) as error:
                    raise ValueError(f"Samplesheet row {index} has invalid FASTA input: {error}")
                if normalised_hash in seen_normalised_hashes:
                    os.unlink(staged_path)
                    warnings.append(
                        f"Skipped samplesheet row {index}: normalised FASTA content matches "
                        f"row {seen_normalised_hashes[normalised_hash]}"
                    )
                    continue
                seen_normalised_hashes[normalised_hash] = index
                if changes:
                    warnings.append(
                        f"Sanitised FASTA referenced by samplesheet row {index}: {source_path} "
                        f"({'; '.join(changes)})"
                    )
            else:
                shutil.copy2(input_path, staged_path)

            sample_id = (row.get(id_column) or "").strip()
            unique_id = unique_sample_id(sample_id, used_ids)
            if unique_id != sample_id:
                warnings.append(f"Renamed duplicate sample ID on row {index}: {sample_id} -> {unique_id}")

            row[id_column] = unique_id
            row[fasta_column] = staged_path
            rows.append(row)

    if not rows:
        raise ValueError("Samplesheet does not contain any data rows")

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    write_warnings(warning_path, warnings)


def sanitise_directory(directory, required, warning_path):
    fasta_files = [
        entry.path
        for entry in os.scandir(directory)
        if entry.is_file() and entry.name.lower().endswith(FASTA_SUFFIXES)
    ]
    if required and not fasta_files:
        raise ValueError(f"No FASTA files were found in {directory}")

    warnings = []
    seen_normalised_hashes = {}
    for fasta_file in fasta_files:
        normalised_hash, changes = sanitise_in_place(fasta_file)
        if normalised_hash in seen_normalised_hashes:
            os.unlink(fasta_file)
            warnings.append(
                f"Skipped duplicate FASTA file {fasta_file}: normalised content matches "
                f"{seen_normalised_hashes[normalised_hash]}"
            )
            continue
        seen_normalised_hashes[normalised_hash] = fasta_file
        if changes:
            warnings.append(f"Sanitised FASTA file: {fasta_file} ({'; '.join(changes)})")
    write_warnings(warning_path, warnings)


def main():
    command, *arguments = sys.argv[1:]
    if command == "directory" and len(arguments) == 3:
        directory, required, warning_path = arguments
        sanitise_directory(directory, required == "true", warning_path)
    elif command == "samplesheet" and len(arguments) == 5:
        sanitise_samplesheet(*arguments)
    else:
        raise ValueError(f"Unknown or invalid sanitisation input: {command}")


if __name__ == "__main__":
    main()
