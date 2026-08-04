# Demo guide — Intelligent PII Anonymization Platform

Use **only** fictional samples under `samples/fictional/`. Never paste real personal data.

> This project is a demonstration tool. Automated PII detection can produce false positives or miss sensitive information. Users must review all results before sharing anonymized documents.

---

## Prerequisites

- Docker Desktop (WSL2 recommended on Windows)
- Ports `3000` (web) and `8000` (API) free on `127.0.0.1`
- Optional: regenerate samples with `python scripts/generate_fictional_samples.py`

---

## Start the stack

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

```bash
cp .env.example .env
docker compose up --build -d
```

Wait until `docker compose ps` shows postgres and api as healthy (often 1–3 minutes on first build; the API image is large because it includes spaCy, Tesseract, and OpenCV).

- Frontend: http://localhost:3000
- API health: http://localhost:8000/api/v1/health

---

## 3–5 minute demonstration sequence

1. **Start the stack** and open http://localhost:3000. Point out the demonstration warning and system health.
2. **Paste fictional text** — click “Load fictional example” (Casey Okafor / Northstar Demo Clinic) or paste from `samples/fictional/fictional-text-example.txt`.
3. **Analyze** and show explainable detections: category, confidence, detection source.
4. **Reject one detection** (for example a phone number) to show human control.
5. **Add one manual entity** by selecting text in the preview and using “Add manual entity from selection”.
6. **Choose masking or pseudonymization** on an accepted email, then generate anonymized text. Show that the rejected span is unchanged.
7. **Upload** `samples/fictional/fictional-text-document.pdf`. Open PDF review and analyze.
8. **Show coordinate overlays** on the PDF preview; accept detections you intend to remove.
9. **Generate true redaction**, open the result summary, and note verification status.
10. **Upload** `fictional-scanned-document.pdf` or `fictional-id-card.png`. Analyze and show OCR confidence / source labels.
11. **Generate irreversible pixel/scanned redaction** and download the output artifact.
12. **Download the safe JSON audit report** — emphasize it contains counts and categories, not raw values.
13. **Delete now** — confirm the job becomes inaccessible.
14. **Explain privacy and security**: local OCR, no paid AI API, temporary storage, TTL, logging exclusions, and that UUIDs are not authentication.

---

## 60-second version

1. Load fictional text → analyze → reject one entity → anonymize with masking.
2. Upload fictional text PDF → analyze → redact → show verification.
3. Delete now → state that detection is imperfect and review is mandatory.

---

## Key points to say

- Detection is hybrid and explainable — not an LLM black box.
- Humans remain in the loop; pending detections are treated as transformable until rejected (call this out).
- PDFs/images use irreversible redaction; text also supports masking and pseudonymization.
- Scanned pages are rebuilt as rasters so hidden text cannot survive under annotations.
- Nothing here is a compliance certification.
- Temporary data expires and can be deleted immediately.

---

## Sample files

| File | Demo use |
|------|----------|
| `fictional-text-example.txt` | Pasted text |
| `fictional-text-document.pdf` | Embedded-text PDF |
| `fictional-scanned-document.pdf` | OCR PDF |
| `fictional-mixed-document.pdf` | Mixed pages |
| `fictional-id-card.png` | Image OCR |
| `fictional-contact-sheet.jpg` | JPEG OCR |

All samples are synthetic. See `samples/fictional/README.md`.

---

## Stop the stack

```powershell
docker compose down
```

Temporary uploads live in the Docker volume `api_uploads`. To also remove volumes (destroys local temp data and the Compose Postgres database):

```powershell
# WARNING: deletes Compose volumes for this project, including postgres_data and api_uploads.
docker compose down -v
```
