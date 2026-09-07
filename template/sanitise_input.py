#!/usr/bin/env python3
"""Validate and normalise inputs staged for proteinfold."""

import csv
import hashlib
import os
import re
import shutil
import sys
import tempfile


FASTA_SUFFIXES = (".fa", ".fasta")
YAML_SUFFIXES = (".yaml", ".yml")
HEADERLESS_SEQUENCE_ID_LENGTH = 6
PROTEIN_ALPHABET = frozenset("ACDEFGHIKLMNPQRSTVWYX")
DNA_ALPHABET = frozenset("ACTGN")
RNA_ALPHABET = frozenset("ACUGN")
SMILES_PATTERN = re.compile(r"[A-Za-z0-9@+\-\[\]\(\)=#\$%:./\\*]+")
SMILES_DANGLING_TOKENS = frozenset("-/\\=#$%:.")
ENTITY_TYPES = frozenset(("protein", "ccd", "smiles", "dna", "rna"))
NON_PROTEIN_METHODS = frozenset(("alphafold3", "boltz"))
POLYMER_ENTITY_TYPES = frozenset(("protein", "dna", "rna"))
BOLTZ_ENTITY_TYPES = POLYMER_ENTITY_TYPES | {"ligand"}


class IncompatibleEntityError(ValueError):
    """An otherwise valid entity is unsupported by the selected method."""


class NoCompatibleInputsError(ValueError):
    """Input filtering left nothing that can be submitted."""


class InputValidationError(ValueError):
    """Input is malformed and must not be submitted to ProteinFold."""


def strip_whitespace(value):
    return "".join(
        char for char in value if not char.isspace() and char not in {"\ufeff", "\u200b"}
    )


def infer_entity_type(header, sequence):
    """Match the untagged FASTA inference used by ProteinFold converters."""
    fields = header.lower().split("|") if header else []
    if len(fields) > 1 and fields[1] in ENTITY_TYPES:
        return fields[1]
    if ":" in sequence:
        chains = sequence.split(":")
        return (
            "protein"
            if all(chain and set(chain) <= PROTEIN_ALPHABET for chain in chains)
            else "unknown"
        )

    residues = set(sequence)
    if residues <= RNA_ALPHABET:
        return "rna"
    if residues <= DNA_ALPHABET:
        return "dna"
    if residues <= PROTEIN_ALPHABET and not residues <= (DNA_ALPHABET | {"U"}):
        return "protein"
    if SMILES_PATTERN.fullmatch(sequence):
        return "smiles"
    return "unknown"


def entity_type_is_supported(entity_type, af_method):
    return entity_type == "protein" or af_method in NON_PROTEIN_METHODS


def validate_entity_sequence(entity_type, sequence, allow_protein_chains=True):
    if entity_type == "protein":
        if not allow_protein_chains and ":" in sequence:
            raise ValueError(
                "Protein sequence contains a chain separator; use an id list for identical chains"
            )
        chains = sequence.split(":")
        if any(not chain for chain in chains):
            raise ValueError("Protein sequence contains an empty chain")
        invalid_residues = "".join(
            sorted(set(sequence.replace(":", "")) - PROTEIN_ALPHABET)
        )
        if invalid_residues:
            raise ValueError(
                f"Protein sequence contains invalid amino acid character(s): "
                f"{invalid_residues}"
            )
    elif entity_type == "dna" and not set(sequence) <= DNA_ALPHABET:
        raise ValueError("DNA sequence contains invalid nucleotide characters")
    elif entity_type == "rna" and not set(sequence) <= RNA_ALPHABET:
        raise ValueError("RNA sequence contains invalid nucleotide characters")
    elif entity_type == "smiles":
        if not SMILES_PATTERN.fullmatch(sequence):
            raise ValueError("SMILES sequence contains unsupported characters")
        if sequence[0] in SMILES_DANGLING_TOKENS or sequence[-1] in SMILES_DANGLING_TOKENS:
            raise ValueError("SMILES sequence has dangling bond or component syntax")


def load_boltz_yaml(path):
    try:
        import yaml
    except ImportError as error:
        raise InputValidationError("PyYAML is unavailable for Boltz YAML validation") from error

    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as error:
        raise InputValidationError(f"Invalid Boltz YAML: {error}") from error

    return data, yaml


def normalise_boltz_yaml(data):
    """Validate Boltz entities and normalise their sequence values in place."""

    if not isinstance(data, dict):
        raise InputValidationError("Boltz YAML must contain a top-level mapping")
    sequences = data.get("sequences")
    if not isinstance(sequences, list) or not sequences:
        raise InputValidationError("Boltz YAML must contain a non-empty sequences list")

    chain_ids = set()
    removed_whitespace = 0
    removed_terminal_stops = 0
    for index, entry in enumerate(sequences, start=1):
        if not isinstance(entry, dict) or len(entry) != 1:
            raise InputValidationError(
                f"Boltz YAML sequence entry {index} must be a single-key mapping"
            )
        entity_type, details = next(iter(entry.items()))
        if entity_type not in BOLTZ_ENTITY_TYPES:
            raise InputValidationError(
                f"Boltz YAML sequence entry {index} has unsupported entity type: {entity_type}"
            )
        if not isinstance(details, dict):
            raise InputValidationError(
                f"Boltz YAML {entity_type} entry {index} must be a mapping"
            )

        identifiers = details.get("id")
        identifiers = identifiers if isinstance(identifiers, list) else [identifiers]
        if not identifiers or any(
            not isinstance(value, str) or not value.strip() for value in identifiers
        ):
            raise InputValidationError(f"Boltz YAML {entity_type} entry {index} is missing id")
        if len(set(identifiers)) != len(identifiers) or chain_ids.intersection(identifiers):
            raise InputValidationError("Boltz YAML chain ids must be unique")
        chain_ids.update(identifiers)

        if entity_type in POLYMER_ENTITY_TYPES:
            sequence = details.get("sequence")
            if not isinstance(sequence, str) or not sequence.strip():
                raise InputValidationError(
                    f"Boltz YAML {entity_type} entry {index} is missing sequence"
                )
            normalised_sequence = strip_whitespace(sequence)
            if not normalised_sequence:
                raise InputValidationError(
                    f"Boltz YAML {entity_type} entry {index} is missing sequence"
                )
            removed_whitespace += len(sequence) - len(normalised_sequence)
            if entity_type == "protein":
                if normalised_sequence.endswith("*"):
                    normalised_sequence = normalised_sequence[:-1]
                    removed_terminal_stops += 1
            try:
                validate_entity_sequence(
                    entity_type, normalised_sequence, allow_protein_chains=False
                )
            except ValueError as error:
                raise InputValidationError(
                    f"Boltz YAML {entity_type} entry {index}: {error}"
                ) from error
            details["sequence"] = normalised_sequence
        else:
            ligand_keys = [key for key in ("smiles", "ccd") if key in details]
            if len(ligand_keys) != 1:
                raise InputValidationError(
                    f"Boltz YAML ligand entry {index} must contain exactly one of smiles or ccd"
                )
            ligand_key = ligand_keys[0]
            ligand_value = details[ligand_key]
            if ligand_key == "smiles":
                if not isinstance(ligand_value, str):
                    raise InputValidationError(
                        f"Boltz YAML ligand entry {index} smiles must be a string"
                    )
                normalised_smiles = strip_whitespace(ligand_value)
                if not normalised_smiles:
                    raise InputValidationError(
                        f"Boltz YAML ligand entry {index} is missing smiles"
                    )
                removed_whitespace += len(ligand_value) - len(normalised_smiles)
                try:
                    validate_entity_sequence("smiles", normalised_smiles)
                except ValueError as error:
                    raise InputValidationError(
                        f"Boltz YAML ligand entry {index}: {error}"
                    ) from error
                details["smiles"] = normalised_smiles
            else:
                ccd_codes = ligand_value if isinstance(ligand_value, list) else [ligand_value]
                if not ccd_codes or any(
                    not isinstance(code, str) or not code.strip() for code in ccd_codes
                ):
                    raise InputValidationError(
                        f"Boltz YAML ligand entry {index} ccd must be a string or "
                        "non-empty list of strings"
                    )
                normalised_codes = [code.strip() for code in ccd_codes]
                removed_whitespace += sum(
                    len(code) - len(normalised)
                    for code, normalised in zip(ccd_codes, normalised_codes)
                )
                details["ccd"] = (
                    normalised_codes if isinstance(ligand_value, list) else normalised_codes[0]
                )

    changes = []
    if removed_terminal_stops:
        changes.append(
            f"removed terminal stop codon from {removed_terminal_stops} Boltz YAML sequence(s)"
        )
    if removed_whitespace:
        changes.append(
            f"removed {removed_whitespace} whitespace character(s) from Boltz YAML input data"
        )
    return changes


def validate_boltz_yaml(path):
    data, _ = load_boltz_yaml(path)
    normalise_boltz_yaml(data)


def sanitise_boltz_yaml(source_path, destination_path):
    data, yaml = load_boltz_yaml(source_path)
    changes = normalise_boltz_yaml(data)
    if changes:
        with open(destination_path, "w", encoding="utf-8") as destination:
            yaml.safe_dump(data, destination, allow_unicode=True, sort_keys=False)
    else:
        shutil.copy2(source_path, destination_path)
    return changes


def sanitise_boltz_yaml_in_place(path):
    data, yaml = load_boltz_yaml(path)
    changes = normalise_boltz_yaml(data)
    if not changes:
        return changes
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), delete=False) as temporary:
        temporary_path = temporary.name
    try:
        with open(temporary_path, "w", encoding="utf-8") as destination:
            yaml.safe_dump(data, destination, allow_unicode=True, sort_keys=False)
        os.replace(temporary_path, path)
        return changes
    except BaseException:
        os.unlink(temporary_path)
        raise


def sanitise_fasta(source_path, destination_path, af_method=None):
    has_record = False
    record_has_content = False
    blank_lines = 0
    trailing_blank_lines = 0
    normalised_headers = 0
    normalised_line_endings = 0
    removed_sequence_whitespace = 0
    removed_terminal_stops = 0
    added_header = None
    record_sequence = []
    record_header = None
    # Hash ordered record sequences, excluding headers and sequence line wrapping.
    digest = hashlib.sha256()

    with open(source_path, encoding="utf-8-sig", newline="") as source, open(
        destination_path, "w", encoding="utf-8"
    ) as destination:

        def write(value):
            destination.write(value)

        def write_sequence(raw_line, line_number, is_final_line):
            nonlocal removed_sequence_whitespace
            nonlocal removed_terminal_stops
            nonlocal record_has_content

            unstripped_sequence = strip_whitespace(raw_line)
            sequence = unstripped_sequence
            chains = sequence.split(":")
            if any(not chain for chain in chains):
                raise ValueError(f"Sequence on line {line_number} has an empty chain")
            stripped_chains = list(chains)
            for index, chain in enumerate(chains):
                if chain.endswith("*") and (index < len(chains) - 1 or is_final_line):
                    stripped_chains[index] = chain[:-1]
            stripped_sequence = ":".join(stripped_chains)
            if (
                stripped_sequence != sequence
                and stripped_sequence
                and infer_entity_type(
                    record_header, "".join(record_sequence) + stripped_sequence
                ) == "protein"
            ):
                removed_terminal_stops += sum(
                    chain.endswith("*") and (index < len(chains) - 1 or is_final_line)
                    for index, chain in enumerate(chains)
                )
                sequence = stripped_sequence
            if not sequence:
                return

            normalised_sequence = f"{sequence}\n"
            removed_sequence_whitespace += len(raw_line.rstrip("\r\n")) - len(
                unstripped_sequence
            )
            record_sequence.append(sequence)
            write(normalised_sequence)
            record_has_content = True

        pending_sequence = None

        def flush_pending_sequence(is_final_line):
            nonlocal pending_sequence
            if pending_sequence is None:
                return
            write_sequence(*pending_sequence, is_final_line)
            pending_sequence = None

        def finish_record():
            sequence = "".join(record_sequence)
            entity_type = infer_entity_type(record_header, sequence)
            if entity_type == "unknown":
                raise ValueError("FASTA record contains an unsupported entity sequence")
            validate_entity_sequence(entity_type, sequence)
            if af_method == "alphafold2" and entity_type == "protein" and "X" in sequence:
                raise IncompatibleEntityError(
                    "FASTA record contains X, which AlphaFold2 cannot run"
                )
            if af_method and not entity_type_is_supported(entity_type, af_method):
                raise IncompatibleEntityError(
                    f"FASTA record is {entity_type} input, which is only supported by "
                    "AlphaFold3 or Boltz"
                )
            digest.update(hashlib.sha256(sequence.encode("utf-8")).digest())

        for line_number, raw_line in enumerate(source, start=1):
            if raw_line.endswith("\r\n") or raw_line.endswith("\r"):
                normalised_line_endings += 1
            line = raw_line.strip()
            if not line:
                blank_lines += 1
                trailing_blank_lines += 1
                continue
            trailing_blank_lines = 0
            if line.startswith(">"):
                flush_pending_sequence(True)
                if has_record and not record_has_content:
                    raise ValueError(
                        f"FASTA record before line {line_number} has no sequence/content"
                    )
                if has_record:
                    finish_record()
                header = line[1:].strip()
                if not header:
                    raise ValueError(f"FASTA header on line {line_number} is empty")
                normalised_header = f">{header}\n"
                if raw_line != normalised_header:
                    normalised_headers += 1
                record_sequence.clear()
                record_header = header
                write(normalised_header)
                has_record = True
                record_has_content = False
                continue
            if not has_record:
                sequence = strip_whitespace(raw_line)
                if not sequence:
                    continue
                header_sequence = sequence[:-1] if sequence.endswith("*") else sequence
                added_header = header_sequence[:HEADERLESS_SEQUENCE_ID_LENGTH]
                record_sequence.clear()
                record_header = None
                write(f">{added_header}\n")
                has_record = True
            flush_pending_sequence(False)
            pending_sequence = (raw_line, line_number)

        flush_pending_sequence(True)
    if not has_record:
        raise ValueError("No FASTA header found")
    if not record_has_content:
        raise ValueError("Final FASTA record has no sequence/content")
    finish_record()

    changes = []
    blank_lines -= trailing_blank_lines
    if blank_lines:
        changes.append(f"removed {blank_lines} blank line(s)")
    if normalised_line_endings:
        changes.append(f"normalised line endings in {normalised_line_endings} line(s)")
    if normalised_headers:
        changes.append(f"normalised {normalised_headers} FASTA header(s)")
    if added_header:
        changes.append(f"added FASTA header {added_header}")
    if removed_terminal_stops:
        changes.append(
            f"removed terminal stop codon from {removed_terminal_stops} FASTA record(s)"
        )
    if removed_sequence_whitespace:
        changes.append(
            f"removed {removed_sequence_whitespace} whitespace character(s) from sequence data"
        )
    return digest.hexdigest(), changes


def sanitise_in_place(path, af_method=None):
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), delete=False) as temporary:
        temporary_path = temporary.name
    try:
        normalised_hash, changes = sanitise_fasta(path, temporary_path, af_method)
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


def append_warnings(warning_path, warnings):
    if not warnings:
        return
    if not os.path.exists(warning_path) or os.path.getsize(warning_path) == 0:
        write_warnings(warning_path, warnings)
        return
    with open(warning_path, "a", encoding="utf-8") as handle:
        handle.write("\n" + "\n".join(warnings) + "\n")
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


def normalise_samplesheet_ids(samplesheet_path, warning_path):
    with open(samplesheet_path, encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames or []
        if "id" not in fieldnames:
            raise ValueError("Generated samplesheet does not contain an id column")

        used_ids = set()
        warnings = []
        rows = []
        for row_number, row in enumerate(reader, start=2):
            sample_id = (row.get("id") or "").strip()
            unique_id = unique_sample_id(sample_id, used_ids)
            if unique_id != sample_id:
                warnings.append(
                    f"Renamed duplicate generated sample ID on row {row_number}: "
                    f"{sample_id} -> {unique_id}"
                )
            row["id"] = unique_id
            rows.append(row)

    with tempfile.NamedTemporaryFile(
        dir=os.path.dirname(os.path.abspath(samplesheet_path)),
        mode="w",
        encoding="utf-8",
        newline="",
        delete=False,
    ) as temporary:
        writer = csv.DictWriter(temporary, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        temporary_path = temporary.name
    os.replace(temporary_path, samplesheet_path)
    append_warnings(warning_path, warnings)


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
                warnings.append(
                    f"Skipped samplesheet row {index}: YAML input is only supported by Boltz"
                )
                continue

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
                    normalised_hash, changes = sanitise_fasta(input_path, staged_path, af_method)
                except IncompatibleEntityError as error:
                    if os.path.exists(staged_path):
                        os.unlink(staged_path)
                    warnings.append(f"Skipped samplesheet row {index}: {error}")
                    continue
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
                changes = sanitise_boltz_yaml(input_path, staged_path)
                if changes:
                    warnings.append(
                        f"Sanitised Boltz YAML referenced by samplesheet row {index}: "
                        f"{source_path} ({'; '.join(changes)})"
                    )

            sample_id = (row.get(id_column) or "").strip()
            unique_id = unique_sample_id(sample_id, used_ids)
            if unique_id != sample_id:
                warnings.append(f"Renamed duplicate sample ID on row {index}: {sample_id} -> {unique_id}")

            row[id_column] = unique_id
            row[fasta_column] = staged_path
            rows.append(row)

    if not rows:
        write_warnings(warning_path, warnings)
        raise NoCompatibleInputsError(
            "No compatible inputs remain after filtering the samplesheet"
        )

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    write_warnings(warning_path, warnings)


def sanitise_directory(directory, warning_path, af_method=None):
    yaml_files = sorted(
        entry.path
        for entry in os.scandir(directory)
        if entry.is_file() and entry.name.lower().endswith(YAML_SUFFIXES)
    )
    fasta_files = sorted(
        entry.path
        for entry in os.scandir(directory)
        if entry.is_file() and entry.name.lower().endswith(FASTA_SUFFIXES)
    )
    warnings = []
    if af_method == "boltz":
        for yaml_file in yaml_files:
            changes = sanitise_boltz_yaml_in_place(yaml_file)
            if changes:
                warnings.append(
                    f"Sanitised Boltz YAML file: {yaml_file} ({'; '.join(changes)})"
                )
    seen_normalised_hashes = {}
    for fasta_file in fasta_files:
        try:
            normalised_hash, changes = sanitise_in_place(fasta_file, af_method)
        except IncompatibleEntityError as error:
            os.unlink(fasta_file)
            warnings.append(f"Skipped incompatible FASTA file {fasta_file}: {error}")
            continue
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
    if fasta_files and not any(os.path.exists(path) for path in fasta_files):
        write_warnings(warning_path, warnings)
        raise NoCompatibleInputsError(
            "No compatible FASTA inputs remain after filtering"
        )
    write_warnings(warning_path, warnings)


def check_output_collisions(samplesheet_path, output_directory, af_method):
    """Refuse only sample IDs that already have outputs for the selected method."""
    method_directory = os.path.join(output_directory, af_method)

    with open(samplesheet_path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        id_column = next(
            (name for name in (reader.fieldnames or []) if name.strip().lower() == "id"),
            None,
        )
        if not id_column:
            raise InputValidationError("Samplesheet has no id column for output checking")
        sample_ids = {
            (row.get(id_column) or "").strip() for row in reader
        } - {""}

    output_directories = [method_directory]
    if af_method == "alphafold2":
        output_directories.append(os.path.join(method_directory, "split_msa_prediction"))
    names = {
        name
        for directory in output_directories
        if os.path.isdir(directory)
        for name in os.listdir(directory)
    }
    collisions = {
        sample_id
        for sample_id in sample_ids
        if any(
            name == sample_id
            or name.startswith(f"{sample_id}_")
            or name.startswith(f"{sample_id}.")
            for name in names
        )
    }

    if collisions:
        joined = ", ".join(sorted(collisions))
        raise InputValidationError(
            f"Existing {af_method} outputs would be overwritten for input ID(s): {joined}"
        )


def main():
    command, *arguments = sys.argv[1:]
    if command == "directory" and len(arguments) == 3:
        sanitise_directory(*arguments)
    elif command == "samplesheet-ids" and len(arguments) == 2:
        normalise_samplesheet_ids(*arguments)
    elif command == "samplesheet" and len(arguments) == 5:
        sanitise_samplesheet(*arguments)
    elif command == "output-collisions" and len(arguments) == 3:
        check_output_collisions(*arguments)
    else:
        raise ValueError(f"Unknown or invalid sanitisation input: {command}")


if __name__ == "__main__":
    try:
        main()
    except (InputValidationError, NoCompatibleInputsError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(2)
