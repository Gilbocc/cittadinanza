from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from prompt_compiler import compile_all_prompts, compile_prompt_text


class PromptCompilerTests(unittest.TestCase):
    def test_compile_prompt_text_replaces_project_placeholder(self):
        compiled = compile_prompt_text("Header\n{{src/mapping.json}}\nFooter\n", PROJECT_ROOT)

        self.assertIn('"numero_anno_ruolo"', compiled)
        self.assertIn("Header", compiled)
        self.assertIn("Footer", compiled)
        self.assertNotIn("{{src/mapping.json}}", compiled)

    def test_compile_prompt_text_raises_for_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            compile_prompt_text("{{src/does_not_exist.py}}", PROJECT_ROOT)

    def test_compile_all_prompts_writes_compiled_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            compiled_paths = compile_all_prompts(PROJECT_ROOT, output_dir=output_dir)

            expected_file = output_dir / "2_map_instructions.txt"
            self.assertIn(expected_file, compiled_paths)
            self.assertTrue(expected_file.exists())

            content = expected_file.read_text(encoding="utf-8")
            self.assertIn("def generate_classification_template", content)
            self.assertNotIn("{{src/templates.py}}", content)


if __name__ == "__main__":
    unittest.main()