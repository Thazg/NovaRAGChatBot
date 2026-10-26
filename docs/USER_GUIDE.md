# Using Nova

Nova answers questions using documents in your account. It retrieves passages and asks the configured model to answer from that context. Verify important claims against your original documents: a cited answer can still be incomplete or incorrect.

## Start a workspace

1. Register or sign in.
2. Wait for the startup checks. If the API is temporarily unavailable, use **Retry session**; signing in again is appropriate when the session has expired.
3. Choose **Upload a document**. Supported types are PDF, DOCX, Markdown, RST, TXT, Python and Jupyter notebooks. The standard upload limit is 25 MB.
4. Wait for indexing to finish before asking document questions. Parser/security checks can reject encrypted, malformed or unsafe files.

The initial gate opens the workspace once it finds uploaded documents. In **Docs**, check whether each file is indexed. A file shown as **Not indexed** may have an unfinished or failed job; that label does not claim the job is still running. The list updates after document operations; use **Retry loading documents** after a listing failure or **Re-index all documents** to retry indexing. A storage error is shown separately from an empty library.

## Ask a grounded question

Use a concrete question, such as “What assumptions does the method make?” or “Summarize the limitations of this experiment.” Choose **Ask** beside a document to scope future questions to that file. The scope appears above the composer. Clear it to search across your account's indexed documents.

Press **Enter** to send and **Shift+Enter** for a new line. Enter used to confirm an IME composition does not send the message. Responses stream into the conversation. **Stop generation** keeps the partial answer marked incomplete. Switching to a different conversation also stops the current browser operation.

If the connection breaks, the provider fails, or the model invents an evidence ID, the response remains marked interrupted. Choose **Regenerate answer** to try again. Nova does not silently replay an uncertain chat request. Regeneration replaces the latest assistant attempt while keeping its user question. While waiting for the first answer text, only **Nova is thinking...** is shown; sources are displayed after completion.

## Read source references

A response may include text such as:

```text
Source: methods.pdf, Page 4, Lines 12–18
```

These locations come from extracted document metadata. For PDFs, page numbers are 1-based PDF pages and lines count the extracted lines on that page, including blank lines. They may differ from printed page numbers, a PDF viewer's wrapping or the visual reading order of a multi-column page. For text-like formats, lines refer to extracted text and no PDF page is invented.

Open your original document and inspect the cited area. Source references deliberately do not require a document link or viewer. **Copy**, **Share** and conversation **Export** retain readable filename/page/line references. Share uses the browser's native share feature when available, otherwise it copies the text. Your browser controls which share targets are available.

Older answers cannot gain missing provenance retroactively. Re-index an older document and ask a new question to obtain page/line metadata.

## Search for additional PDFs

Type `search for retrieval evaluation` or `tìm kiếm đánh giá truy xuất`, or choose **Search web** when offered. Nova searches for PDFs, validates downloads, then indexes newly added files in the background. The chat shows indexing status and only announces readiness after the returned job finishes. If the job fails, read the error and retry/reindex or choose a different file.

Stopping the browser request does not roll back a download or cancel a background job already accepted by the server. Refresh **Docs** to see the resulting files. Search progress text is local status rather than a saved model answer.

## Manage documents and conversations

**Docs** lists your documents and provides Ask, Download, Delete and Re-index all actions. Download saves the original uploaded file under its display filename and works even before indexing finishes. A failed download shows an error and can be retried. The list updates after document operations; use Retry if loading fails. **Settings → Knowledge base** includes document summaries and clear-all controls. A summary may be truncated for very long documents. Confirm destructive operations carefully; they are different from hiding a conversation in the UI.

Rename, duplicate, pin or export a conversation from its action menu. **Export** downloads a TXT transcript, including readable source locations. Global conversation search is available through **Ctrl/Cmd+K**. **Ctrl/Cmd+N** creates a conversation; **Ctrl/Cmd+/** focuses the composer. Escape closes search or stops the active generation/search operation.

Account export in **Settings → Privacy & data** downloads JSON containing account metadata, preferences, conversations, source evidence and document metadata. It does not include original document binaries. Keep copies of your uploaded originals separately.

## Preferences, account and privacy

Settings can change language, response style, display name, nickname and custom instructions. These preferences are saved to your account. Theme and sidebar preferences are also kept in the browser. Tokens, chats, selected document filenames, custom instructions and account identity are not stored in the browser preference blob. Avatars last for the current session and are not synced to the server.

Browser voice input is optional and depends on SpeechRecognition support and microphone permission. Its availability and data handling belong to your browser's speech service; typed input remains available.

Changing your password revokes other refresh sessions. Existing access tokens expire according to the configured access-token lifetime; password change is not an instant cancellation of every request already in progress.

Deleting a document prevents it from being used for future retrieval while cleanup finishes. If deletion or account cleanup reports a failure/pending state, keep the session and retry the action. A failed account deletion does not automatically sign you out, so you can finish cleanup. Existing conversation text and retained operational snapshots follow the server's retention policy; removing a document is not a promise to rewrite old answers.

## When an answer is weak

- Check that the intended document is indexed and the scope is correct.
- Ask for a narrower section or a concrete fact, rather than relying on a broad question.
- Inspect sources for claims the model made; source locations are not an accuracy guarantee.
- Re-index legacy documents if page/line metadata is missing.
- If no document supports the question, upload a relevant source or search for another PDF.

The current retrieval benchmark still shows poor abstention on unrelated questions. Do not rely on Nova always recognizing that an answer is absent from the library. See the [evaluation guide](../backend/evaluation/README.md) for measured quality and its limits, and [production persistence](PRODUCTION_PERSISTENCE.md) for storage/retention behavior.
