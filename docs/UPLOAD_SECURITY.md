# File upload and remote PDF security

## Local upload validation pipeline

Files are never indexed directly from the client-provided filename. The API performs this sequence:

1. Normalize the display filename and enforce the extension allowlist.
2. Stream into a temporary quarantine file while enforcing `MAX_UPLOAD_BYTES`.
3. Compare the declared MIME type with the extension allowlist.
4. Validate the actual structure: PDF signature plus strict parser, DOCX ZIP/package structure, notebook JSON, or UTF-8 text.
5. Enforce PDF page/object/decompression/extracted-text limits and reject encryption, embedded files, JavaScript, automatic actions, XFA, and page actions.
6. Enforce DOCX entry, expanded-size, compression-ratio, path, active-content, embedded-content, and external-relationship limits.
7. Reject the EICAR test signature and submit the quarantined bytes to ClamAV when configured.
8. Atomically rename the accepted file to a server-generated UUID while retaining the original name only as display metadata.
9. Persist the artifact to B2 when a shared worker is configured, enqueue
   parsing and BM25 indexing, and return a job ID for progress polling.
   Embedding generation occurs only when hybrid retrieval is explicitly enabled.

Rejected temporary files are removed. Index failures remove the stored artifact and rebuild the user's index from accepted files.

## Remote PDF and SSRF controls

Remote search results are untrusted. Every initial request and redirect is validated independently:

- only HTTP and HTTPS;
- no URL credentials or control characters;
- only ports 80 and 443;
- `localhost`, `.localhost`, and `.local` names are rejected;
- every DNS answer must be a globally routable IP (IPv4 and IPv6);
- environment proxy variables are disabled for the downloader;
- automatic redirects are disabled, with at most five manually validated redirects;
- the connected socket peer must be available and globally routable, which fails closed on private-IP DNS rebinding;
- 4xx/security failures are not retried;
- response MIME, declared length, streamed byte count, `%PDF-` signature, strict PDF structure, complexity, and malware checks are all enforced.

Downloaded PDFs also receive UUID storage names. Source URLs are metadata and are never used as filesystem paths.

## Malware scanning requirements

Development can run with scanning optional:

```env
MALWARE_SCAN_REQUIRED=false
```

Before public uploads are enabled, provision a reachable ClamAV daemon and fail closed:

```env
CLAMAV_HOST=<private scanner hostname>
CLAMAV_PORT=3310
MALWARE_SCAN_REQUIRED=true
```

If the scanner is unavailable or returns an indeterminate result while required mode is enabled, the upload is rejected. Confirm the deployment with the standard EICAR test file; never use real malware for this check.

## Resource limits

| Variable | Default |
|---|---:|
| `MAX_UPLOAD_BYTES` | 25 MiB |
| `MAX_PDF_PAGES` | 500 |
| `MAX_PDF_OBJECTS` | 100,000 |
| `MAX_PDF_DECOMPRESSED_STREAM_BYTES` | 10 MiB per Flate stream |
| `MAX_PDF_EXTRACTED_CHARS` | 5,000,000 |
| `MAX_ARCHIVE_ENTRIES` | 2,000 |
| `MAX_ARCHIVE_UNCOMPRESSED_BYTES` | 100 MiB |
| `MAX_ARCHIVE_COMPRESSION_RATIO` | 100 |
| `MAX_NOTEBOOK_CELLS` | 2,000 |

## Verification commands

```bash
python -m pytest backend/tests/test_security_controls.py -q
python -m pytest backend/tests -q
```

The security suite covers local/private/link-local/metadata IPs, mixed DNS answers, private redirects, unverifiable/private connected peers, MIME spoofing, streaming limits, malformed and active PDFs, DOCX bombs/external relationships, EICAR, required-scanner failure, and UUID storage.

## Residual risk

This is a denylist-based public-URL downloader because search results can come from many domains. A stricter production deployment should add a curated domain allowlist or an isolated egress proxy. ClamAV also does not replace sandboxing or content-disarm-and-reconstruction for highly sensitive document workflows.
