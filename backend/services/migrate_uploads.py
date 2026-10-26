"""Explicit, non-destructive local upload cutover to durable storage."""
import argparse


def migrate_uploads(user_id: str) -> int:
    from api.routes import documents
    from services.index_jobs import _user_index_lock
    from services.document_lifecycle import deleted_documents, mark_deleted
    from services.remote_storage import download_bytes, upload_file, file_exists
    import json

    with _user_index_lock(user_id):
        from services.account_lifecycle import ensure_writable
        ensure_writable(user_id)
        directory = documents._user_uploads_dir(user_id)
        local_manifest = directory / "document_manifest.json"
        manifest = json.loads(local_manifest.read_bytes()) if local_manifest.exists() else {}
        remote = download_bytes(f"uploads/{user_id}/document_manifest.json", required=True)
        manifest.update(json.loads(remote) if remote else {})
        deleted = deleted_documents(user_id)
        # Carry local deletion barriers into the shared backend before uploads.
        mark_deleted(user_id, deleted)
        migrated = 0
        for path in directory.iterdir():
            if not path.is_file() or path.suffix.lower() not in documents.SUPPORTED_EXTENSIONS or path.name in deleted:
                continue
            key = f"uploads/{user_id}/{path.name}"
            if file_exists(key, required=True):
                if download_bytes(key, required=True) != path.read_bytes():
                    raise RuntimeError(f"Conflicting remote upload {path.name}; neither copy was changed")
            else:
                if not upload_file(key, path):
                    raise RuntimeError(f"Could not migrate {path.name}; local original was preserved")
                migrated += 1
            manifest.setdefault(path.name, {"original_name": path.name})
        for name in deleted:
            manifest.pop(name, None)
        documents._save_manifest(manifest, user_id)
        return migrated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args()
    # This is a CLI path, so reject paths before constructing per-user folders.
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args.user_id):
        parser.error("user-id must be a flat account ID")
    print(f"Migrated {migrate_uploads(args.user_id)} uploads; local originals preserved. Reindex next.")


if __name__ == "__main__":
    main()
