from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.metrics import evaluate_dataset

DEFAULT_DATASET = Path(__file__).with_name("dataset.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Nova retrieval and citation quality offline.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.90)
    parser.add_argument("--min-mrr", type=float, default=0.80)
    parser.add_argument("--min-citation-precision", type=float, default=0.90)
    parser.add_argument("--min-citation-recall", type=float, default=0.90)
    parser.add_argument("--min-faithfulness", type=float, default=0.60)
    parser.add_argument("--min-unanswerable-accuracy", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    results = evaluate_dataset(dataset, k=args.k)
    report = json.dumps(results, ensure_ascii=False, indent=2)
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")

    passed = (
        results["recall_at_k"] >= args.min_recall
        and results["mrr"] >= args.min_mrr
        and results["citation_precision"] >= args.min_citation_precision
        and results["citation_recall"] >= args.min_citation_recall
        and results["faithfulness"] >= args.min_faithfulness
        and results["unanswerable_accuracy"] >= args.min_unanswerable_accuracy
    )
    if not passed:
        print("Evaluation thresholds were not met.")
        return 1
    print("Evaluation thresholds passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
