import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

from config.settings import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
UPLOADS_DIR = Path(settings.UPLOAD_FOLDER).resolve()
LEGACY_UPLOADS_DIR = (BACKEND_DIR / "uploads").resolve()

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".rst", ".txt", ".py", ".ipynb", ".docx"}
TEXT_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".py"}


@dataclass
class Document:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def clean_text(text: str) -> str:
    if not text:
        return ""

    return "".join(
        ch for ch in text
        if not (0xD800 <= ord(ch) <= 0xDFFF)
    )


def file_metadata(file_path: Path) -> Dict[str, Any]:
    return {
        "source": str(file_path),
        "file_path": str(file_path),
        "file_name": file_path.name,
        "file_type": file_path.suffix.lower(),
    }


def add_metadata(text: str, file_path: Path) -> Document:
    text = clean_text(text)
    spans = []
    offset = 0
    for number, line in enumerate(text.splitlines(keepends=True), start=1):
        if line.strip():
            spans.append({"line": number, "start": offset, "end": offset + len(line.rstrip("\r\n"))})
        offset += len(line)
    return Document(text=text, metadata={**file_metadata(file_path), "_line_spans": spans})


def load_text(file_path: Path) -> List[Document]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return [add_metadata(text, file_path)]


def load_pdf(file_path: Path) -> List[Document]:
    if not PDF_AVAILABLE:
        return []
    reader = PdfReader(str(file_path))
    documents = []
    for page_number, page in enumerate(reader.pages, start=1):
        text, spans = normalize_pdf_with_lines(page.extract_text() or "")
        if text:
            document = add_metadata(text, file_path)
            document.metadata["page"] = page_number
            document.metadata["_line_spans"] = spans
            documents.append(document)
    return documents


def normalize_pdf_text(text: str) -> str:
    return normalize_pdf_with_lines(text)[0]


def normalize_pdf_with_lines(text: str) -> tuple[str, list[dict]]:
    """Keep 1-based extracted line numbers while normalizing retrieval text."""
    text = text.replace("\u00ad", "")
    for ligature, replacement in {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}.items():
        text = text.replace(ligature, replacement)
    normalized = ""
    spans = []
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if re.search(r"\w-$", normalized) and re.match(r"\w", line):
            normalized = normalized[:-1]
            if spans:
                spans[-1]["end"] -= 1
        elif normalized:
            normalized += " "
        start = len(normalized)
        normalized += line
        spans.append({"line": number, "start": start, "end": len(normalized)})
    return normalized, spans


def load_notebook(file_path: Path) -> List[Document]:
    notebook = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
    cells = []

    for cell in notebook.get("cells", []):
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)

        source = source.strip()
        if source:
            cells.append(source)

    return [add_metadata("\n\n".join(cells), file_path)]


def load_docx(file_path: Path) -> List[Document]:
    if not DOCX_AVAILABLE:
        return []
    document = DocxDocument(str(file_path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return [add_metadata("\n\n".join(paragraphs), file_path)]


def load_file(file_path: Path) -> List[Document]:
    file_path = Path(file_path).resolve()
    suffix = file_path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        documents = load_text(file_path)
    elif suffix == ".pdf":
        documents = load_pdf(file_path)
    elif suffix == ".ipynb":
        documents = load_notebook(file_path)
    elif suffix == ".docx":
        documents = load_docx(file_path)
    else:
        return []

    return documents


def iter_supported_files(input_dir: Path) -> List[Path]:
    input_dir = Path(input_dir).resolve()
    if not input_dir.exists():
        return []

    return sorted(
        file_path
        for file_path in input_dir.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def load_documents() -> List[Document]:
    documents: List[Document] = []
    seen_paths: set[str] = set()

    for base_dir in [UPLOADS_DIR, LEGACY_UPLOADS_DIR]:
        if not base_dir.exists():
            continue
        for file_path in iter_supported_files(base_dir):
            resolved = str(file_path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            documents.extend(load_file(file_path))

    return documents


def print_load_summary(documents: List[Document]) -> None:
    counts = {}

    for document in documents:
        file_type = document.metadata.get("file_type", "unknown")
        counts[file_type] = counts.get(file_type, 0) + 1

    print(f"Loaded {len(documents)} documents from uploads")
    for file_type, count in sorted(counts.items()):
        print(f"- {file_type}: {count}")


if __name__ == "__main__":
    documents = load_documents()
    print_load_summary(documents)
