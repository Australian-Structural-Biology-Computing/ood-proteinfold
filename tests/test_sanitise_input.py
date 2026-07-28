import contextlib
import importlib.util
import io
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
                    "normalised 1 sequence line(s)",
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

    def test_rejects_sequence_before_header(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "invalid.fasta"
            destination = directory / "output.fasta"
            source.write_text("ACDE\n")

            with self.assertRaisesRegex(ValueError, "before the first FASTA header"):
                SANITISE_INPUT.sanitise_fasta(source, destination)


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


if __name__ == "__main__":
    unittest.main()
