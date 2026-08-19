# arXiv benchmark annotation guide

## Scope

The benchmark contains 100 English questions over 10 version-pinned arXiv PDFs:
10 questions per paper, comprising 9 answerable questions and 1 deliberately
unanswerable question. Questions cover contributions, architecture, training,
experimental setup, results, metrics, and limitations.

## Ground-truth policy

For every answerable question, the annotation must contain:

1. A concise reference answer supported by the paper.
2. A verbatim `evidence_match` copied from the PDF extraction.
3. A paper slug that limits evidence resolution to the intended PDF.
4. A review state.

`build_dataset.py` resolves each evidence string against the checksum-locked PDF
extraction and turns the matching PDF page into the relevance label. The build
fails when evidence is absent, a paper slug is unknown, IDs are duplicated, or
the question count is not exactly 100. Page-level labels are used because a
correct retrieval does not depend on which overlapping chunk contains the same
sentence.

An unanswerable question must ask about a claim that the scoped paper does not
make. It has an empty evidence match and no relevant page ID. It must not be a
trick caused only by ambiguous wording.

## Review protocol

The committed labels have completed a single-reviewer verification pass:

- the question is answerable from the intended PDF, or intentionally absent;
- the reference answer agrees with the cited evidence;
- the evidence span resolves to at most two pages;
- versions and SHA-256 values match `checksums.json`;
- all 100 IDs and question-to-paper assignments are unique and complete.

The metadata intentionally records `independent_review_status` as
`pending_human_reviewer`. A second reviewer should independently mark each row
as `accept`, `revise`, or `reject`, then record disagreements and adjudication.
Until that happens, the repository must not describe the benchmark as
double-annotated or independently human-reviewed.

## Reproduction

Run from `backend`:

```bash
python evaluation/arxiv_corpus/download_papers.py
python evaluation/arxiv_corpus/extract_corpus.py
python evaluation/arxiv_corpus/build_dataset.py
python -m evaluation.run --k 5 --output evaluation/results.json
```

The downloader rejects any PDF whose SHA-256 or page count differs from the
committed lock. PDF binaries, extracted text, and the generated evaluation
dataset remain local build artifacts; the repository commits only the source
manifest, checksum lock, annotations, methodology, and aggregate/per-query
results.
