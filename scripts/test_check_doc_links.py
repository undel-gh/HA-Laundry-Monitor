"""Standalone regression tests for the documentation link checker."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from check_doc_links import check_links, parse_document


class TestDocLinks(TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path: str, source: str) -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        return Path(path)

    def test_local_paths_and_unicode_fragments(self) -> None:
        source = self.write(
            "README.md",
            "[guide](docs/User%20guide.md#русский-раздел)\n"
            "[license](LICENSE)\n"
            "[absolute repo path](/docs/User%20guide.md#spin-mode)\n",
        )
        self.write("LICENSE", "license")
        self.write(
            "docs/User guide.md",
            "# Русский раздел\n\n## Spin *mode*\n",
        )
        self.assertEqual(check_links(self.root, [source]), ([], 3, 0))

    def test_missing_path_and_fragment(self) -> None:
        source = self.write(
            "README.md",
            "[missing](missing.md)\n\n[anchor](docs/guide.md#missing)\n",
        )
        self.write("docs/guide.md", "# Heading")
        errors, local, external = check_links(self.root, [source])
        self.assertEqual((local, external), (2, 0))
        self.assertEqual(len(errors), 2)
        self.assertIn("README.md:1: missing path", errors[0])
        self.assertIn("README.md:3: missing heading/anchor", errors[1])

    def test_inline_and_fenced_examples_ignored(self) -> None:
        document = parse_document(
            "# Actual\n\n"
            "`[example](missing.md)`\n\n"
            "~~~md\n# Not a heading\n[example](missing.md)\n~~~\n"
            "\n    [indented](missing.md)\n"
        )
        self.assertEqual(document.anchors, {"actual"})
        self.assertEqual(document.links, [])

    def test_duplicate_headings_and_explicit_anchor(self) -> None:
        source = self.write(
            "README.md",
            "# Test `code`\n\n# Test `code`\n\n"
            '<a id="custom"></a>\n\n'
            "[first](#test-code) [second](#test-code-1) [id](#custom)",
        )
        self.assertEqual(check_links(self.root, [source]), ([], 3, 0))

    def test_reference_links_images_and_table_links(self) -> None:
        source = self.write(
            "README.md",
            "[reference][doc]\n\n"
            "[doc]: docs/guide.md#section\n\n"
            "| A |\n| --- |\n| [table](docs/guide.md#section) |\n\n"
            "![image](icon.png)\n",
        )
        self.write("docs/guide.md", "# Section")
        self.write("icon.png", "image")
        self.assertEqual(check_links(self.root, [source]), ([], 3, 0))

    def test_external_urls_are_not_local_paths(self) -> None:
        source = self.write(
            "README.md",
            "[external](https://github.com/example/repo/blob/main/missing.md)\n"
            "[mail](mailto:docs@example.org)\n"
            "[protocol relative](//example.org/missing.md)\n",
        )
        self.assertEqual(check_links(self.root, [source]), ([], 0, 3))

    def test_escape_rejected_and_non_markdown_fragment_allowed(self) -> None:
        source = self.write(
            "README.md",
            "[outside](../outside.md)\n[code](script.py#L1)\n",
        )
        self.write("script.py", "pass")
        errors, local, external = check_links(self.root, [source])
        self.assertEqual((local, external), (2, 0))
        self.assertEqual(len(errors), 1)
        self.assertIn("link escapes repository", errors[0])

    def test_directory_readme_fragment(self) -> None:
        source = self.write("README.md", "[directory](docs/#index)")
        self.write("docs/README.md", "# Index")
        self.assertEqual(check_links(self.root, [source]), ([], 1, 0))

    def test_html_link_and_image(self) -> None:
        source = self.write(
            "README.md", '<a href="docs/guide.md#title">Guide</a>\n\n'
            '<img src="missing.png" alt="missing">\n'
        )
        self.write("docs/guide.md", "# Title")
        errors, local, external = check_links(self.root, [source])
        self.assertEqual((local, external), (2, 0))
        self.assertEqual(len(errors), 1)
        self.assertIn("missing path: missing.png", errors[0])
