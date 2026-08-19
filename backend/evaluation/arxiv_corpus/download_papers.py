from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import requests
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
PDF_DIR = ROOT / "pdfs"
LOCK_PATH = ROOT / "checksums.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path, retries: int = 3) -> None:
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "NovaRAGBenchmark/1.0 (academic corpus downloader)"},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.content
            if not payload.startswith(b"%PDF-"):
                raise ValueError(f"Downloaded payload is not a PDF: {url}")
            destination.write_bytes(payload)
            return
        except Exception:
            if attempt == retries:
                raise
            time.sleep(attempt * 2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the pinned arXiv PDF corpus.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--update-lock",
        action="store_true",
        help="Replace checksums.json after intentionally reviewing a new PDF revision.",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not LOCK_PATH.is_file() and not args.update_lock:
        raise ValueError("Missing checksums.json; use --update-lock only for an intentional corpus update.")
    expected_lock = (
        json.loads(LOCK_PATH.read_text(encoding="utf-8")) if LOCK_PATH.is_file() else {"papers": []}
    )
    expected_by_file = {item["pdf_file"]: item for item in expected_lock["papers"]}
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    observed_lock: dict[str, object] = {"manifest_version": manifest["version"], "papers": []}
    for paper in manifest["papers"]:
        destination = PDF_DIR / paper["pdf_file"]
        if args.force or not destination.exists():
            print(f"Downloading {paper['arxiv_id']}{paper['version']} -> {destination.name}")
            _download(paper["pdf_url"], destination)
        reader = PdfReader(destination)
        if not reader.pages:
            raise ValueError(f"PDF contains no pages: {destination}")
        observed = {
            "arxiv_id": paper["arxiv_id"],
            "version": paper["version"],
            "pdf_file": paper["pdf_file"],
            "sha256": _sha256(destination),
            "bytes": destination.stat().st_size,
            "pages": len(reader.pages),
        }
        observed_lock["papers"].append(observed)
        if not args.update_lock:
            expected = expected_by_file.get(paper["pdf_file"])
            if expected is None:
                raise ValueError(f"No checksum lock entry for {destination.name}")
            if observed["sha256"] != expected["sha256"]:
                raise ValueError(
                    f"Checksum mismatch for {destination.name}: expected "
                    f"{expected['sha256']}, got {observed['sha256']}"
                )
            if observed["pages"] != expected["pages"]:
                raise ValueError(
                    f"Page-count mismatch for {destination.name}: expected "
                    f"{expected['pages']}, got {observed['pages']}"
                )
        print(f"Verified {destination.name}: {len(reader.pages)} pages")

    if args.update_lock:
        LOCK_PATH.write_text(json.dumps(observed_lock, indent=2) + "\n", encoding="utf-8")
        print(f"Updated checksum lock: {LOCK_PATH}")
    else:
        print(f"All PDFs match checksum lock: {LOCK_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
