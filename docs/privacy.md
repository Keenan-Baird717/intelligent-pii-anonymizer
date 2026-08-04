# Privacy — Intelligent PII Anonymization Platform

This document explains, in plain language, how the platform handles your documents
and the personal information it detects. It complements [security.md](security.md).

> **This project is a demonstration tool. Automated PII detection can produce false
> positives or miss sensitive information. Users must review all results before
> sharing anonymized documents.**

---

## In short

- Everything runs **locally** through Docker Compose on your own machine.
- **No paid cloud AI APIs** are used, and there is **no primary LLM detector**.
- Your document **content, the detected values, and any pseudonym mappings are
  never written to the database or the logs.**
- Uploaded files are stored temporarily with random names and are **deleted
  automatically after 60 minutes**, or immediately when you choose **delete now**.
- Detection is **imperfect** — always review before you rely on an output.

---

## 1. What data is processed

You can either **paste text** or **upload a document** (`PDF`, `PNG`, `JPG`,
`JPEG`). The platform can:

- analyze the content to detect likely PII (names, emails, phone numbers, Canadian
  postal codes, SIN, credit-card numbers, and similar),
- let you **review** each detection (accept, reject, edit, or add your own),
- **anonymize/redact** accepted items,
- show a **safe result summary**, and
- provide **downloads**: the anonymized output plus a JSON **audit report** that
  excludes raw detected values.

The personal information *inside* your document is processed only to detect and
redact it. It is not sold, shared, or sent to any third party.

## 2. Where processing happens

All processing happens **on your machine** inside local containers (a Python API,
a Next.js web app, and a PostgreSQL database) orchestrated by Docker Compose.

- **No paid cloud AI API is required or used.**
- **No primary LLM-based detector** — detection uses spaCy + Microsoft Presidio and
  deterministic pattern/checksum recognizers (e.g., Luhn for credit cards).
- **OCR runs locally** using Tesseract (English only for this MVP). Images and
  scanned PDFs never leave your machine for OCR.

## 3. Temporary storage

Uploaded files are streamed to a controlled temporary directory and stored under
**random internal names** (your original filename is never used as a path and is
never persisted). Any OCR intermediate images are written to a separate work
subfolder with random names and removed after processing. The upload directory is
not served to the browser as static content.

## 4. How long data is kept (retention)

- **Default retention is 60 minutes** (`UPLOAD_TTL_MINUTES`). After that, the
  uploaded file, generated artifacts, OCR work files, and the job's database row
  are removed by an automatic cleanup task, with a reconciliation pass at startup.
- **Delete now:** you can remove everything for a job immediately, which deletes the
  source file, any generated outputs, OCR work files, and the database record.
- **Pasted text is never stored at all** — it exists only for the duration of the
  request and is discarded when the response is sent.

> Deletion uses a normal file delete, **not** a secure/forensic wipe. On shared or
> recoverable storage, remnants may persist until overwritten (see §12).

## 5. What PostgreSQL stores — and does not store

**Stored (metadata only):**

- Job info: validated file type, byte size, page count, image dimensions,
  timestamps, expiry, a random storage key, and safe analysis-coverage counts.
- Detection *metadata*: entity type/category, confidence, detection source,
  recognizer name, checksum-valid flag, text offsets, page number, redaction
  rectangles, review status, chosen anonymization method, and safe OCR metadata
  (source kind, OCR confidence, low-confidence flag).

**Never stored:**

- The actual detected **values** (the database schema has no column for them).
- Your **document text** or **OCR text**.
- **Pseudonym mappings**.
- **Original filenames** or absolute file paths.

There is also **no `AuditEvent` table and no separate audit database** — the audit
report is generated on demand from the safe metadata above. (No schema migration
was needed to remove sensitive fields; the schema was designed minimal from the
start.)

## 6. OCR locality and detection approach

OCR is performed locally with Tesseract; the raw OCR text and its intermediate
files are used only in-memory/temporarily and are never logged or stored. Detection
combines spaCy NLP, Presidio recognizers, and deterministic validators. **No paid
AI services and no LLM detector** are involved.

## 7. What we exclude from logs

Logs are structured operational records containing only safe fields such as a
request ID, job ID, validated type, byte size, page/pixel counts, DPI, durations,
counts, and error codes. Logs **exclude** your document content, detected values,
OCR text, original filenames, storage keys, and absolute paths. Any client-supplied
request ID is sanitized before use.

## 8. What the audit report excludes

The downloadable JSON audit report is built from safe metadata only. It includes
counts and coverage (detections by category, review outcomes, method counts,
verification status, warnings) but **excludes raw detected values, document text,
OCR text, filenames, storage keys, and pseudonym mappings**. The report is
validated before download to reject any sensitive field.

## 9. Your controls

- Review **every** detection before anonymizing.
- Accept, reject, edit, or manually add detections and draw redaction regions.
- Choose the anonymization method (redaction, masking, replacement, or
  request-scoped pseudonymization).
- Download the anonymized output and the audit report.
- **Delete all data for a job immediately** at any time.

## 10. Browser-state and clipboard limitations

- The anonymized output and result summaries are sent with
  `Cache-Control: no-store, private`, but your **browser may still keep data in
  memory**, and using "Save as" or OS-level swap is outside our control. Prefer a
  private/trusted machine, and clear downloads when done.
- If you **copy** anonymized text to the clipboard, that content leaves the app's
  control — the operating system clipboard may retain it and other apps may read it.
- The pasted-text workflow keeps your original text in the **browser tab**; closing
  or reloading the tab discards it.

## 11. UUIDs are not access control

Jobs are identified by hard-to-guess random UUIDs. **A UUID is not a password and
is not authorization.** In this MVP there is **no login and no per-user access
control**, so anyone who can reach the local API and knows a job's UUID could act on
that job. This is why the app is intended for **local, single-user** use, with ports
bound to your local machine only.

## 12. File-recovery limitations

Deletion removes directory entries but does **not** securely erase the underlying
disk blocks. Until the storage is overwritten, deleted uploads or outputs could in
principle be recovered with forensic tools. For sensitive material, use
encrypted, ephemeral storage and short retention.

## 13. Backup limitations

This MVP has **no privacy-designed backup system**. If you add your own backups of
the database or volumes, those backups may capture job **metadata** and any files
present at backup time — plan backup encryption, minimization, and deletion
accordingly.

## 14. Known detection limitations

- Automated detection has **false positives** (flagging non-PII) and **false
  negatives** (missing real PII), especially for unusual formats or context.
- **OCR accuracy varies** with scan quality, handwriting, fonts, resolution, and
  layout; low-confidence OCR is flagged in the UI but can still be wrong.
- Redaction is verified automatically (re-extraction and re-OCR), but verification
  is not infallible for unusual encodings, ligatures, or complex layouts.
- Manual redaction rectangles cover the region you draw only.

**Always review the anonymized output yourself before sharing it.**

## 15. Production recommendations (not in this demo)

This is a demonstration build. A real, privacy-respecting deployment would add
authentication and authorization, TLS/HTTPS, malware scanning and sandboxed
processing, distributed rate limiting, coordinated cleanup across instances, secret
management, monitoring and audit logging, encrypted and minimized backups, an
incident-response process, and strict multi-tenant isolation. See
[security.md](security.md#14-production-requirements-not-implemented-in-phase-8)
for the full list. **None of these are implemented in the Phase 8 MVP.**
