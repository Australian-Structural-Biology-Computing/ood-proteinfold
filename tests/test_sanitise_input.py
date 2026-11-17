import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest



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
                SANITISE_INPUT.sanitise_fasta(source, destination, "boltz2")

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
            for method in ("alphafold3", "boltz2"):
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

    def test_keeps_valid_af3_json_and_skips_invalid_jobs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            warning_path = directory / "WARNING.txt"
            valid = directory / "job.json"
            valid.write_text(
                '{"name": "job", "sequences": '
                '[{"protein": {"id": ["A"], "sequence": "ACDE"}}]}'
            )
            multi = directory / "multi.json"
            multi.write_text('[{"name": "a", "sequences": []}, {"name": "b", "sequences": []}]')
            malformed = directory / "malformed.json"
            malformed.write_text("{not json")

            with contextlib.redirect_stderr(io.StringIO()):
                SANITISE_INPUT.sanitise_directory(directory, warning_path)

            self.assertTrue(valid.exists())
            self.assertFalse(multi.exists())
            self.assertFalse(malformed.exists())
            warnings = warning_path.read_text()
            self.assertIn("multi.json", warnings)
            self.assertIn("one job per file", warnings)
            self.assertIn("malformed.json", warnings)
            self.assertIn("not valid JSON", warnings)


class Af3JsonTests(unittest.TestCase):
    def test_accepts_single_job_and_returns_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "job.json"
            path.write_text(
                '{"name": "myjob", "sequences": '
                '[{"protein": {"id": ["A"], "sequence": "ACDE"}}]}'
            )
            self.assertEqual(SANITISE_INPUT.validate_af3_json(path), "myjob")

    def test_accepts_nameless_single_job(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "job.json"
            path.write_text('{"sequences": [{"protein": {"id": ["A"], "sequence": "ACDE"}}]}')
            self.assertIsNone(SANITISE_INPUT.validate_af3_json(path))

    def test_rejects_multiple_jobs_in_one_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "jobs.json"
            path.write_text('[{"name": "a", "sequences": []}, {"name": "b", "sequences": []}]')
            with self.assertRaises(SANITISE_INPUT.InputValidationError) as raised:
                SANITISE_INPUT.validate_af3_json(path)
            self.assertIn("one job per file", str(raised.exception))

    def test_rejects_non_job_objects_and_missing_sequences(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "notes.json"
            path.write_text('{"notes": "hello"}')
            with self.assertRaises(SANITISE_INPUT.InputValidationError) as raised:
                SANITISE_INPUT.validate_af3_json(path)
            self.assertIn("sequences list", str(raised.exception))

    def test_rejects_malformed_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "broken.json"
            path.write_text("{not json")
            with self.assertRaises(SANITISE_INPUT.InputValidationError) as raised:
                SANITISE_INPUT.validate_af3_json(path)
            self.assertIn("not valid JSON", str(raised.exception))


class SanitiseSamplesheetTests(unittest.TestCase):
    def test_filters_duplicate_and_incompatible_entries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "first.fasta").write_text(">first|protein\nACDE\n")
            (directory / "duplicate.fasta").write_text(">duplicate|protein\nAC DE\n")
            (directory / "dna.fasta").write_text(">dna|dna\nACTGN\n")
            (directory / "input.json").write_text('{"notes": "not a job"}')
            samplesheet = directory / "samplesheet.csv"
            samplesheet.write_text(
                "id,fasta\n"
                "first,first.fasta\n"
                "duplicate,duplicate.fasta\n"
                "dna,dna.fasta\n"
                "json,input.json\n"
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
            self.assertIn("Skipped samplesheet row 5", warnings)
            self.assertIn("no sequences list", warnings)

    def test_keeps_non_protein_entries_and_valid_af3_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "protein.fasta").write_text(">protein|protein\nACDE\n")
            (directory / "smiles.fasta").write_text(">ligand|smiles\nCCO\n")
            (directory / "job.json").write_text(
                '{"name": "job", "sequences": '
                '[{"protein": {"id": ["A"], "sequence": "ACDE"}}]}'
            )
            samplesheet = directory / "samplesheet.csv"
            samplesheet.write_text(
                "id,fasta\n"
                "protein,protein.fasta\n"
                "smiles,smiles.fasta\n"
                "job,job.json\n"
            )
            output_path = directory / "sanitised.csv"

            SANITISE_INPUT.sanitise_samplesheet(
                samplesheet, output_path, directory / "inputs", directory / "WARNING.txt", "alphafold3"
            )

            with output_path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["id"] for row in rows], ["protein", "smiles", "job"])
            self.assertIn("job.json", rows[-1]["fasta"])


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
