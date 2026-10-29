import csv
import hashlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from PTM.tools.buscador_texto import buscar_texto


class TextSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, relative, text, encoding="utf-8"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return path

    def search(self, text, **kwargs):
        events = list(buscar_texto(self.root, text, **kwargs))
        return [data for kind, data in events if kind == "match"], events[-1][1]

    def test_recursive_literal_search_reports_file_line_and_excerpt(self):
        path = self.write("nested/source.py", 'hello\nAPP_VERSION = "1.2.3"\n')
        self.write("nested/other.json", '{"app_version": "1.2.3"}\n')
        matches, stats = self.search("APP_VERSION")
        self.assertEqual(len(matches), 2)
        self.assertIn((str(path), 2, 'APP_VERSION = "1.2.3"'), matches)
        self.assertEqual(stats["reason"], "complete")

    def test_handles_utf8_utf16_utf32_and_windows_text_without_extension(self):
        for index, encoding in enumerate(("utf-8-sig", "utf-16", "utf-32", "cp1252")):
            self.write(f"file{index}", "primera\nTexto de acción\n", encoding)
        matches, _ = self.search("acción")
        self.assertEqual(len(matches), 4)
        self.assertTrue(all(match[1] == 2 for match in matches))

    def test_filters_case_patterns_binary_and_git_metadata(self):
        self.write("one.py", "Needle\nneedle\n")
        self.write("two.json", "Needle\n")
        self.write("three.txt", "Needle\n")
        self.write(".git/config", "Needle\n")
        (self.root / "binary.py").write_bytes(b"\x00\x01Needle")
        matches, stats = self.search("Needle", case_sensitive=True, patterns="*.py;*.json")
        self.assertEqual(len(matches), 2)
        self.assertEqual(stats["binary"], 1)
        self.assertTrue(all(".git" not in match[0] for match in matches))

    def test_result_limit_stops_with_explicit_reason(self):
        self.write("source.txt", "match\n" * 20)
        matches, stats = self.search("match", max_results=3)
        self.assertEqual(len(matches), 3)
        self.assertEqual(stats["reason"], "limit")

    def test_cancellation_while_reading_a_file(self):
        self.write("source.txt", "match\n" * 20)
        cancel = threading.Event()
        events = buscar_texto(self.root, "match", cancel=cancel)
        self.assertEqual(next(events)[0], "match")
        cancel.set()
        remaining = list(events)
        self.assertEqual(remaining[-1][0], "done")
        self.assertEqual(remaining[-1][1]["reason"], "cancelled")
        self.assertFalse(any(kind == "match" for kind, _ in remaining))

    def test_long_line_excerpt_contains_the_match(self):
        self.write("long.txt", "a" * 2000 + "target" + "b" * 2000)
        matches, _ = self.search("target")
        self.assertIn("target", matches[0][2])
        self.assertLessEqual(len(matches[0][2]), 601)

    def test_catalog_registration_and_git_content_hash(self):
        root = Path(__file__).resolve().parents[1]
        data = (root / "PTM/guide.csv").read_bytes()
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8")), delimiter=";"))
        tool = next(row for row in rows if row["slug"] == "buscador_texto")
        self.assertTrue((root / "PTM" / tool["ruta"]).is_file())
        self.assertEqual(tool["modo"], "Integrado")
        meta = json.loads((root / "PTM/guide_meta.json").read_text())
        self.assertEqual(meta["guide_rows"], len(rows))
        self.assertEqual(meta["guide_sha"], hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest())


if __name__ == "__main__":
    unittest.main()
