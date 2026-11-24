"""Read-only check of links in tracked repository Markdown documents.

Parse CommonMark with GFM tables, validate relative paths and heading
fragments, and ignore external URLs. No network requests are made.
"""

from __future__ import annotations

import os
import subprocess
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass(frozen=True)
class LocalLink:
    destination: str
    line: int


@dataclass
class Document:
    anchors: set[str]
    links: list[LocalLink]


def heading_slug(text: str) -> str:
    """Generate the GitHub-style heading IDs used by repository docs."""
    return "".join(
        "-" if char.isspace() else char
        for char in text.strip().lower()
        if char in "-_"
        or char.isspace()
        or unicodedata.category(char)[0] not in "CPS"
    )


def heading_text(token: Token) -> str:
    """Extract visible heading text, not its Markdown markup or link URL."""
    if token.children is not None:
        return "".join(heading_text(child) for child in token.children)
    if token.type in {"text", "code_inline"}:
        return token.content
    if token.type in {"softbreak", "hardbreak"}:
        return " "
    return ""


class HtmlReferences(HTMLParser):
    """Collect explicitly declared HTML anchors, links and images."""

    def __init__(self, document: Document, line: int) -> None:
        super().__init__(convert_charrefs=True)
        self.document = document
        self.line = line

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if anchor := attributes.get("id"):
            self.document.anchors.add(anchor)
        if tag == "a" and (anchor := attributes.get("name")):
            self.document.anchors.add(anchor)
        attribute = {"a": "href", "img": "src"}.get(tag)
        if attribute and (destination := attributes.get(attribute)):
            self.document.links.append(LocalLink(destination, self.line))


def collect_links(token: Token, document: Document, line: int) -> None:
    """Collect actual parsed links/images, never code examples."""
    if token.map is not None:
        line = token.map[0] + 1
    attribute = {"link_open": "href", "image": "src"}.get(token.type)
    if attribute is not None:
        destination = token.attrGet(attribute)
        if destination:
            document.links.append(LocalLink(destination, line))
    elif token.type in {"html_inline", "html_block"}:
        HtmlReferences(document, line).feed(token.content)

    for child in token.children or []:
        collect_links(child, document, line)


def parse_document(source: str) -> Document:
    """Return heading anchors and link destinations from parsed Markdown."""
    parser = MarkdownIt("commonmark", {"html": True}).enable(
        ["table", "strikethrough"]
    )
    tokens = parser.parse(source)
    document = Document(set(), [])
    heading_ids: set[str] = set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            base = heading_slug(heading_text(tokens[index + 1]))
            anchor = base
            suffix = 1
            while anchor in heading_ids:
                anchor = f"{base}-{suffix}"
                suffix += 1
            heading_ids.add(anchor)
            document.anchors.add(anchor)
        collect_links(token, document, 1)
    return document


def check_links(
    root: Path, files: list[Path]
) -> tuple[list[str], int, int]:
    """Check repository-local links; return errors, local and external counts."""
    root = root.resolve()
    documents: dict[Path, Document] = {}
    errors: list[str] = []
    local_count = external_count = 0

    def document_at(path: Path) -> Document:
        if path not in documents:
            documents[path] = parse_document(path.read_text(encoding="utf-8"))
        return documents[path]

    for file in files:
        source = (root / file).resolve()
        if not source.is_relative_to(root):
            errors.append(f"{file}: Markdown source escapes repository")
            continue
        for link in document_at(source).links:
            location = f"{source.relative_to(root)}:{link.line}"
            try:
                url = urlsplit(link.destination)
            except ValueError as exc:
                errors.append(f"{location}: invalid URL: {exc}")
                continue
            if url.scheme or url.netloc:
                external_count += 1
                continue
            local_count += 1
            path = unquote(url.path)
            if path.startswith("/"):
                target = root / path.lstrip("/")
            elif path:
                target = source.parent / path
            else:
                target = source
            target = target.resolve()
            if not target.is_relative_to(root):
                errors.append(
                    f"{location}: link escapes repository: {link.destination}"
                )
                continue
            if not target.exists():
                errors.append(f"{location}: missing path: {link.destination}")
                continue
            fragment = unquote(url.fragment)
            if not fragment:
                continue
            # Directory links can refer to the rendered README.
            if target.is_dir():
                target = (target / "README.md").resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    errors.append(
                        f"{location}: no directory README: {link.destination}"
                    )
                    continue
            # Non-Markdown targets (e.g. source-code line anchors) are
            # checked for existence only; their fragments are not headings.
            if target.suffix.lower() == ".md":
                if fragment not in document_at(target).anchors:
                    errors.append(
                        f"{location}: missing heading/anchor: "
                        f"{link.destination}"
                    )

    return errors, local_count, external_count


def main() -> int:
    """Scan Git-tracked Markdown in the checked-out repository."""
    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.md"], cwd=root
    )
    files = sorted(Path(os.fsdecode(p)) for p in tracked.split(b"\0") if p)
    errors, local, external = check_links(root, files)
    for error in errors:
        print(error)
    print(
        f"Checked {len(files)} Markdown files, {local} local links; "
        f"skipped {external} external URLs; {len(errors)} errors."
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
