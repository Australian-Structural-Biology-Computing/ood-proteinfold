import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "template" / "pae_mugshots.py"
SPEC = importlib.util.spec_from_file_location("pae_mugshots", MODULE_PATH)
PAE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAE)


def write_matrix(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join("\t".join("%.4f" % abs(i - j) for j in range(size)) + "\n" for i in range(size))
    )


class PaeMugshotTests(unittest.TestCase):
    def layout(self, root, mode_dir=""):
        method = root / "method" / mode_dir
        structure = method / "top_ranked_structures" / "s1.pdb"
        structure.parent.mkdir(parents=True)
        structure.write_text("ATOM\n")
        return method, structure

    def test_picks_lowest_ranked_pae_and_renders_upscaled_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            method, structure = self.layout(Path(temporary), "standard")
            write_matrix(method / "s1" / "paes" / "s1_2_pae.tsv", 3)
            write_matrix(method / "s1" / "paes" / "s1_1_pae.tsv", 5)
            status, png, source, _ = PAE.render_pae(str(structure))
            self.assertEqual(status, "rendered")
            self.assertTrue(source.endswith("s1_1_pae.tsv"))
            self.assertEqual(Path(png), structure.with_name("s1_pae.png"))
            data = Path(png).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(int.from_bytes(data[16:20], "big"), PAE.PLOT_SIZE)
            self.assertEqual(PAE.render_pae(str(structure))[0], "skipped")

    def test_large_matrix_is_downscaled(self):
        with tempfile.TemporaryDirectory() as temporary:
            method, structure = self.layout(Path(temporary))
            write_matrix(method / "s1" / "paes" / "s1_0_pae.tsv", 450)
            rows = PAE.read_matrix(str(method / "s1" / "paes" / "s1_0_pae.tsv"))
            self.assertEqual((len(rows), len(rows[0])), (PAE.PLOT_SIZE, PAE.PLOT_SIZE))
            self.assertEqual(PAE.render_pae(str(structure))[0], "rendered")

    def test_missing_empty_and_malformed_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            method, structure = self.layout(Path(temporary))
            self.assertEqual(PAE.render_pae(str(structure))[0], "missing")
            pae = method / "s1" / "paes" / "s1_0_pae.tsv"
            pae.parent.mkdir(parents=True)
            pae.write_text("")
            self.assertEqual(PAE.render_pae(str(structure))[0], "missing")
            pae.write_text("1\t2\n3\n")
            status, png, _, detail = PAE.render_pae(str(structure))
            self.assertEqual((status, png), ("failed", ""))
            self.assertIn("square", detail)


if __name__ == "__main__":
    unittest.main()
