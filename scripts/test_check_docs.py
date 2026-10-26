"""Standard-library fixtures for the documentation gate, independent of app deps."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from check_docs import api_errors, configuration_errors, link_errors


class DocumentationContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def api_fixture(self):
        self.write("backend/app.py", 'from api.routes import example as exposed\napp.include_router(exposed.router, prefix="/items")\nraise RuntimeError("must not import app")\n')
        self.write("backend/api/routes/example.py", '@router.get("/{item_id}")\nasync def get_item(): pass\n')

    def test_routes_fail_when_added_or_removed_without_updating_the_reference(self):
        self.api_fixture()
        self.write("docs/API_REFERENCE.md", "# API\n")
        self.assertIn("undocumented route GET /items/{}", api_errors(self.root)[0])
        self.write("docs/API_REFERENCE.md", "`GET /items/{id}`\n")
        self.assertEqual(api_errors(self.root), [])
        self.write("backend/api/routes/example.py", "# Removed endpoint\n")
        self.assertIn("stale route GET /items/{}", api_errors(self.root)[0])

    def test_multiple_methods_and_trailing_slash_aliases_are_normalized(self):
        self.api_fixture()
        self.write("backend/api/routes/example.py", '@router.get("/")\n@router.head("")\ndef health(): pass\n')
        self.write("docs/API_REFERENCE.md", "`GET|HEAD /items`\n")
        self.assertEqual(api_errors(self.root), [])

    def test_dynamic_route_expressions_cannot_silently_escape_coverage(self):
        self.api_fixture()
        self.write("backend/api/routes/example.py", '@router.get(dynamic_path)\ndef example(): pass\n')
        self.write("docs/API_REFERENCE.md", "# API\n")
        self.assertIn("requires literal decorator paths", api_errors(self.root)[0])

    def test_settings_are_read_without_importing_environment_or_secrets(self):
        self.write("backend/config/settings.py", 'raise RuntimeError("do not import")\nclass Settings:\n    TOP_K: int = 5\n')
        self.write("docs/CONFIGURATION.md", "# Settings\n")
        self.assertTrue(configuration_errors(self.root))
        self.write("docs/CONFIGURATION.md", "`TOP_K` defaults to 5\n")
        self.assertEqual(configuration_errors(self.root), [])

    def test_missing_links_fail_and_fenced_examples_do_not_become_links(self):
        self.write("README.md", "[Guide](docs/guide.md)\n```text\n[example](not-a-file.md)\n```\n")
        self.assertTrue(link_errors(self.root)[0])
        self.write("docs/guide.md", "# Guide\n")
        self.assertEqual(link_errors(self.root)[0], [])


if __name__ == "__main__":
    unittest.main()
