"""Rebuild one existing account's index through the normal guarded writer."""
from __future__ import annotations

import argparse
import re


def rebuild_index(user_id: str) -> tuple[int, int]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id) or user_id == "__anonymous__":
        raise ValueError("user-id must be a flat, non-anonymous account ID")
    from services.auth import user_exists
    if not user_exists(user_id):
        raise LookupError("Account not found; no index was changed")
    from api.routes.documents import _rebuild_full_index
    # This shared entry point takes the per-user mutation lock, hydrates only
    # that account, honors deletion barriers and publishes immutable revisions.
    return _rebuild_full_index(user_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Existing account ID, not username")
    args = parser.parse_args(argv)
    try:
        documents, chunks = rebuild_index(args.user_id)
    except (ValueError, LookupError) as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        parser.exit(1, f"Reindex failed: {exc}\n")
    print(f"Reindexed account {args.user_id}: {documents} parsed documents/pages, {chunks} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
