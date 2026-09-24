import contextlib
import csv
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

import yaml


MODULE_PATH = Path(__file__).parents[1] / "template" / "sanitise_input.py"
SPEC = importlib.util.spec_from_file_location("sanitise_input", MODULE_PATH)
SANITISE_INPUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SANITISE_INPUT)

class SanitiseFastaTests(unittest.TestCase):
    def test_normalises_headers_sequence_whitespace_and_line_endings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "input.fasta"
            destination = Path(temporary_directory) / "output.fasta"
            source.write_bytes(b"\xef\xbb\xbf  > protein  \r\nAC DE \r\n\r\n")

            _, changes = SANITISE_INPUT.sanitise_fasta(source, destination)

            self.assertEqual(destination.read_text(), ">protein\nACDE\n")
            self.assertEqual(
                changes,
                [
                    "normalised line endings in 3 line(s)",
                    "normalised 1 FASTA header(s)",
                    "removed 2 whitespace character(s) from sequence data",
                ],
            )

    def test_reports_blank_lines_between_records(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "input.fasta"
            destination = Path(temporary_directory) / "output.fasta"
            source.write_text(">protein\nACDE\n\nFG\n")

            _, changes = SANITISE_INPUT.sanitise_fasta(source, destination)

            self.assertIn("removed 1 blank line(s)", changes)

    def test_hash_ignores_headers_and_sequence_line_wrapping(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            first = directory / "first.fasta"
            second = directory / "second.fasta"
            first_output = directory / "first-output.fasta"
            second_output = directory / "second-output.fasta"
            first.write_text(">first description\nACDE\nFG\n")
            second.write_text(">second description\nACDEFG\n")

            first_hash, _ = SANITISE_INPUT.sanitise_fasta(first, first_output)
            second_hash, _ = SANITISE_INPUT.sanitise_fasta(second, second_output)

            self.assertEqual(first_hash, second_hash)

    def test_adds_header_to_headerless_sequence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "headerless.fasta"
            destination = directory / "output.fasta"
            source.write_text("ACDE\n")

            _, changes = SANITISE_INPUT.sanitise_fasta(source, destination)

            self.assertEqual(destination.read_text(), ">ACDE\nACDE\n")
            self.assertIn("added FASTA header ACDE", changes)

    def test_rejects_unsupported_entity_sequence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "invalid.fasta"
            destination = directory / "output.fasta"
            source.write_text(">unknown\nACDE?\n")

            with self.assertRaisesRegex(ValueError, "unsupported entity sequence"):
                SANITISE_INPUT.sanitise_fasta(source, destination)

    def test_rejects_smiles_with_dangling_bond_syntax(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "invalid-smiles.fasta"
            destination = directory / "output.fasta"
            source.write_text(">bad_smiles|smiles\nCCO/\n")

            with self.assertRaisesRegex(ValueError, "dangling bond or component syntax"):
                SANITISE_INPUT.sanitise_fasta(source, destination, "boltz")

    def test_strips_terminal_stop_before_hashing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            plain = directory / "plain.fasta"
            stopped = directory / "stopped.fasta"
            plain_output = directory / "plain-output.fasta"
            stopped_output = directory / "stopped-output.fasta"
            plain.write_text(">protein\nACDE\n")
            stopped.write_text(">protein\nACDE*\n")

            plain_hash, _ = SANITISE_INPUT.sanitise_fasta(plain, plain_output)
            stopped_hash, changes = SANITISE_INPUT.sanitise_fasta(stopped, stopped_output)

            self.assertEqual(plain_hash, stopped_hash)
            self.assertEqual(stopped_output.read_text(), ">protein\nACDE\n")
            self.assertIn("removed terminal stop codon from 1 FASTA record(s)", changes)

    def test_rejects_internal_stop_character(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "internal-stop.fasta"
            destination = directory / "output.fasta"
            source.write_text(">protein|protein\nAC*DE\n")

            with self.assertRaisesRegex(ValueError, r"invalid amino acid character\(s\): \*"):
                SANITISE_INPUT.sanitise_fasta(source, destination)

    def test_accepts_valid_non_protein_entities_for_supported_methods(self):
        inputs = {
            "dna": (">dna\nACTGN\n", "ACTGN"),
            "rna": (">rna\nACUGN\n", "ACUGN"),
            "smiles": (">ligand\nC1=CC=CC=C1\n", "C1=CC=CC=C1"),
            "ccd": (">ligand|ccd\nATP\n", "ATP"),
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for method in ("alphafold3", "boltz"):
                for entity_type, (contents, sequence) in inputs.items():
                    with self.subTest(method=method, entity_type=entity_type):
                        source = directory / f"{method}-{entity_type}.fasta"
                        destination = directory / f"{method}-{entity_type}-output.fasta"
                        source.write_text(contents)

                        SANITISE_INPUT.sanitise_fasta(source, destination, method)

                        self.assertEqual(
                            SANITISE_INPUT.infer_entity_type(
                                "ligand|ccd" if entity_type == "ccd" else None,
                                sequence,
                            ),
                            entity_type,
                        )
                        self.assertEqual(destination.read_text(), contents)

    def test_rejects_non_protein_entities_for_protein_only_methods(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "dna.fasta"
            destination = directory / "output.fasta"
            source.write_text(">dna\nACTGN\n")

            with self.assertRaises(SANITISE_INPUT.IncompatibleEntityError):
                SANITISE_INPUT.sanitise_fasta(
                    source, destination, "alphafold2"
                )


class SanitiseDirectoryTests(unittest.TestCase):
    def test_keeps_first_filename_when_normalised_sequences_match(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            warning_path = directory / "WARNING.txt"
            (directory / "a.fasta").write_text(">first\nACDE\n")
            (directory / "b.fasta").write_text(">second\nAC DE\n")

            with contextlib.redirect_stderr(io.StringIO()):
                SANITISE_INPUT.sanitise_directory(directory, warning_path)

            self.assertTrue((directory / "a.fasta").exists())
            self.assertFalse((directory / "b.fasta").exists())
            self.assertIn(str(directory / "b.fasta"), warning_path.read_text())

    def test_unchanged_boltz_yaml_does_not_create_warning(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_path = directory / "input.yaml"
            warning_path = directory / "WARNING.txt"
            contents = (
                "sequences:\n"
                "  - protein:\n      id: [A, B]\n      sequence: MKTAYIAKQR\n"
                "  - dna:\n      id: C\n      sequence: ACTGN\n"
                "  - rna:\n      id: D\n      sequence: ACUGN\n"
                "  - ligand:\n      id: E\n      smiles: 'C/C=C\\C.CC'\n"
                "  - ligand:\n      id: F\n      ccd: ATP\n"
                "  - ligand:\n      id: G\n      ccd: [NAD, ZN]\n"
            )
            input_path.write_text(contents)

            SANITISE_INPUT.sanitise_directory(directory, warning_path, "boltz")

            self.assertFalse(warning_path.exists())
            self.assertEqual(input_path.read_text(), contents)


class BoltzYamlTests(unittest.TestCase):
    def test_accepts_all_supported_entities_and_ligand_representations(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "input.yaml"
            destination = Path(temporary_directory) / "output.yaml"
            source.write_text(
                "sequences:\n"
                "  - protein:\n      id: [A, B]\n      sequence: MKTAYIAKQR\n"
                "  - dna:\n      id: C\n      sequence: ACTGN\n"
                "  - rna:\n      id: D\n      sequence: ACUGN\n"
                "  - ligand:\n      id: E\n      smiles: 'C/C=C\\C.CC'\n"
                "  - ligand:\n      id: F\n      ccd: ATP\n"
                "  - ligand:\n      id: G\n      ccd: [NAD, ZN]\n"
            )

            changes = SANITISE_INPUT.sanitise_boltz_yaml(source, destination)

            self.assertEqual(changes, [])
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_normalises_all_supported_input_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "input.yaml"
            destination = Path(temporary_directory) / "output.yaml"
            source.write_text(
                "sequences:\n"
                "  - protein:\n      id: A\n      sequence: 'M K T*'\n"
                "  - dna:\n      id: B\n      sequence: 'A C T G'\n"
                "  - rna:\n      id: C\n      sequence: 'A C U G'\n"
                "  - ligand:\n      id: D\n      smiles: 'C C O'\n"
                "  - ligand:\n      id: E\n      ccd: ' ATP '\n"
                "  - ligand:\n      id: F\n      ccd: ['NAD ', ' ZN']\n"
            )

            changes = SANITISE_INPUT.sanitise_boltz_yaml(source, destination)
            data = yaml.safe_load(destination.read_text())

            self.assertEqual(
                changes,
                [
                    "removed terminal stop codon from 1 Boltz YAML sequence(s)",
                    "removed 14 whitespace character(s) from Boltz YAML input data",
                ],
            )
            self.assertEqual(data["sequences"][0]["protein"]["sequence"], "MKT")
            self.assertEqual(data["sequences"][1]["dna"]["sequence"], "ACTG")
            self.assertEqual(data["sequences"][2]["rna"]["sequence"], "ACUG")
            self.assertEqual(data["sequences"][3]["ligand"]["smiles"], "CCO")
            self.assertEqual(data["sequences"][4]["ligand"]["ccd"], "ATP")
            self.assertEqual(data["sequences"][5]["ligand"]["ccd"], ["NAD", "ZN"])

    def test_rejects_invalid_entity_values(self):
        invalid_inputs = {
            "invalid protein": (
                "sequences:\n  - protein:\n      id: A\n      sequence: MKTAY?AKQR\n",
                r"invalid amino acid character\(s\): \?",
            ),
            "colon-delimited protein": (
                "sequences:\n  - protein:\n      id: [A, B]\n      sequence: MKT:AYI\n",
                "use an id list",
            ),
            "invalid dna": (
                "sequences:\n  - dna:\n      id: A\n      sequence: ACTUG\n",
                "invalid nucleotide characters",
            ),
            "invalid rna": (
                "sequences:\n  - rna:\n      id: A\n      sequence: ACUTG\n",
                "invalid nucleotide characters",
            ),
            "invalid smiles": (
                "sequences:\n  - ligand:\n      id: A\n      smiles: CCO?\n",
                "unsupported characters",
            ),
            "empty ccd": (
                "sequences:\n  - ligand:\n      id: A\n      ccd: []\n",
                "non-empty list of strings",
            ),
            "non-string ccd": (
                "sequences:\n  - ligand:\n      id: A\n      ccd: 123\n",
                "string or non-empty list of strings",
            ),
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "input.yaml"
            for name, (contents, message) in invalid_inputs.items():
                with self.subTest(name=name):
                    input_path.write_text(contents)
                    with self.assertRaisesRegex(SANITISE_INPUT.InputValidationError, message):
                        SANITISE_INPUT.validate_boltz_yaml(input_path)

    def test_rejects_invalid_yaml_structure(self):
        invalid_inputs = {
            "empty sequences": "sequences: []\n",
            "unknown entity": "sequences:\n  - carbohydrate:\n      id: A\n",
            "missing id": "sequences:\n  - protein:\n      sequence: ACDE\n",
            "duplicate ids": (
                "sequences:\n"
                "  - protein:\n      id: A\n      sequence: ACDE\n"
                "  - dna:\n      id: A\n      sequence: ACTG\n"
            ),
            "missing sequence": "sequences:\n  - rna:\n      id: A\n",
            "ligand fields": (
                "sequences:\n"
                "  - ligand:\n      id: A\n      smiles: CCO\n      ccd: ATP\n"
            ),
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "input.yaml"
            for name, contents in invalid_inputs.items():
                with self.subTest(name=name):
                    input_path.write_text(contents)
                    with self.assertRaises(SANITISE_INPUT.InputValidationError):
                        SANITISE_INPUT.validate_boltz_yaml(input_path)


class SanitiseSamplesheetTests(unittest.TestCase):
    def test_filters_duplicate_and_incompatible_entries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "first.fasta").write_text(">first|protein\nACDE\n")
            (directory / "duplicate.fasta").write_text(">duplicate|protein\nAC DE\n")
            (directory / "dna.fasta").write_text(">dna|dna\nACTGN\n")
            (directory / "input.yaml").write_text(
                "sequences:\n  - protein:\n      id: A\n      sequence: ACDE\n"
            )
            samplesheet = directory / "samplesheet.csv"
            samplesheet.write_text(
                "id,fasta\n"
                "first,first.fasta\n"
                "duplicate,duplicate.fasta\n"
                "dna,dna.fasta\n"
                "yaml,input.yaml\n"
            )
            output_path = directory / "sanitised.csv"
            warning_path = directory / "WARNING.txt"

            SANITISE_INPUT.sanitise_samplesheet(
                samplesheet, output_path, directory / "inputs", warning_path, "alphafold2"
            )

            with output_path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["id"] for row in rows], ["first"])
            warnings = warning_path.read_text()
            self.assertIn("normalised FASTA content matches row 2", warnings)
            self.assertIn("FASTA record is dna input", warnings)
            self.assertIn("YAML input is only supported by Boltz", warnings)

    def test_keeps_non_protein_and_yaml_entries_for_boltz(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "protein.fasta").write_text(">protein|protein\nACDE\n")
            (directory / "smiles.fasta").write_text(">ligand|smiles\nCCO\n")
            (directory / "input.yaml").write_text(
                "sequences:\n  - protein:\n      id: A\n      sequence: ACDE\n"
            )
            samplesheet = directory / "samplesheet.csv"
            samplesheet.write_text(
                "id,fasta\n"
                "protein,protein.fasta\n"
                "smiles,smiles.fasta\n"
                "yaml,input.yaml\n"
            )
            output_path = directory / "sanitised.csv"

            SANITISE_INPUT.sanitise_samplesheet(
                samplesheet, output_path, directory / "inputs", directory / "WARNING.txt", "boltz"
            )

            with output_path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["id"] for row in rows], ["protein", "smiles", "yaml"])


class NormaliseSamplesheetIdsTests(unittest.TestCase):
    def test_renames_duplicate_generated_ids(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            samplesheet = directory / "samplesheet.csv"
            warning_path = directory / "WARNING.txt"
            samplesheet.write_text(
                "id,fasta\n"
                "protein,one.fasta\n"
                "protein,two.fasta\n"
                "protein,three.fasta\n"
            )

            SANITISE_INPUT.normalise_samplesheet_ids(samplesheet, warning_path)

            self.assertEqual(
                samplesheet.read_text(),
                "id,fasta\nprotein,one.fasta\nprotein-2,two.fasta\nprotein-3,three.fasta\n",
            )
            self.assertIn("protein -> protein-2", warning_path.read_text())


if __name__ == "__main__":
    unittest.main()
