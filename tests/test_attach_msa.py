import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).parents[1] / "template" / "attach_msa.py"
SPEC = importlib.util.spec_from_file_location("attach_msa", MODULE)
ATTACH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ATTACH)


class AttachMsaTests(unittest.TestCase):
    def test_matches_directory_inputs_and_leaves_unmatched_samples_blank(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            for name in ("first.fasta", "second.fasta", "first.a3m"):
                (inputs / name).touch()
            sheet = root / "samplesheet.csv"
            sheet.write_text(f"id,fasta\nfirst,{root}/fasta/first.fasta\nsecond,{root}/fasta/second.fasta\n")
            output = root / "output.csv"
            ATTACH.attach_msa(sheet, output, inputs, "DIRECTORY", "")
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["msa"], str(inputs / "first.a3m"))
            self.assertEqual(rows[1]["msa"], "")

    def test_preserves_per_row_paths_and_matches_original_csv_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("first.fasta", "second.fasta", "first.a3m", "second.a3m"):
                (root / name).touch()
            original = root / "original.csv"
            original.write_text("id,fasta,msa\nfirst,first.fasta,first.a3m\nsecond,second.fasta,\n")
            staged = root / "staged.csv"
            staged.write_text(f"id,fasta,msa\nfirst,{root}/2_first.fasta,first.a3m\nsecond,{root}/3_second.fasta,\n")
            output = root / "output.csv"
            ATTACH.attach_msa(staged, output, original, "SAMPLESHEET_INPUT", "")
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["msa"] for row in rows], [str(root / "first.a3m"), str(root / "second.a3m")])
            self.assertEqual(original.read_text(), "id,fasta,msa\nfirst,first.fasta,first.a3m\nsecond,second.fasta,\n")

    def test_uses_original_names_after_directory_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            (inputs / "my protein.a3m").touch()
            (inputs / "my-protein-2.a3m").touch()
            sheet = root / "samplesheet.csv"
            sheet.write_text(f"id,fasta\none,{root}/fasta/my-protein.fasta\ntwo,{root}/fasta/my-protein-2.fasta\n")
            mapping = root / "mapping.bin"
            mapping.write_bytes(b"my-protein.fasta\0my protein.fasta\0my-protein-2.fasta\0my protein-2.fasta\0")
            output = root / "output.csv"
            ATTACH.attach_msa(sheet, output, inputs, "DIRECTORY", "", mapping)
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["msa"], str(root / "msa_inputs" / "1.a3m"))
            self.assertTrue((root / "msa_inputs" / "1.a3m").exists())
            self.assertEqual(rows[1]["msa"], "")

    def test_matches_from_selected_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            alignments = root / "alignments"
            inputs.mkdir()
            alignments.mkdir()
            (alignments / "complex.a3m").touch()
            sheet = root / "samplesheet.csv"
            sheet.write_text(f"id,fasta\ncomplex,{root}/fasta/complex.fasta\n")
            output = root / "output.csv"
            ATTACH.attach_msa(sheet, output, inputs, "DIRECTORY", alignments)
            with output.open(newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["msa"], str(alignments / "complex.a3m"))

    def test_single_file_rejected_for_multiple_samples(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            msa = root / "alignment.a3m"
            msa.touch()
            sheet = root / "samplesheet.csv"
            sheet.write_text("id,fasta\na,a.fasta\nb,b.fasta\n")
            with self.assertRaisesRegex(ValueError, "one sample"):
                ATTACH.attach_msa(sheet, root / "output.csv", root, "DIRECTORY", msa)
            self.assertFalse((root / "output.csv").exists())

    def test_resolves_fallback_csv_relative_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "foo.a3m").touch()
            sheet = root / "original.csv"
            sheet.write_text("id,fasta\nfoo,foo.fasta\n")
            output = root / "output.csv"
            ATTACH.attach_msa(sheet, output, sheet, "SAMPLESHEET_INPUT", "")
            with output.open(newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["msa"], str(root / "foo.a3m"))

    def test_explicit_file_for_single_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            msa = root / "alignment.a3m"
            msa.touch()
            sheet = root / "samplesheet.csv"
            sheet.write_text("id,fasta\na,a.fasta\n")
            ATTACH.attach_msa(sheet, root / "output.csv", "ACDE", "MANUAL_INPUT", msa)
            with (root / "output.csv").open(newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["msa"], str(msa))


if __name__ == "__main__":
    unittest.main()
