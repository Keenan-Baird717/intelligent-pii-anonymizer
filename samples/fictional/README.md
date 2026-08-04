# Fictional sample files

All files in this directory are **synthetic**. They use obviously fictional names,
`example.com` / `example.org` addresses, and reserved `555` telephone numbers.

| File | Purpose |
|------|---------|
| `fictional-text-example.txt` | Pasted-text / README demo copy |
| `fictional-text-document.pdf` | Embedded-text PDF redaction demo |
| `fictional-scanned-document.pdf` | Image-only scanned PDF + OCR demo |
| `fictional-mixed-document.pdf` | Mixed embedded + scanned pages |
| `fictional-id-card.png` | PNG OCR / image redaction demo |
| `fictional-contact-sheet.jpg` | JPEG OCR / image redaction demo |

Regenerate with:

```bash
python scripts/generate_fictional_samples.py
```

Do not add real documents, real personal data, EXIF GPS, or production uploads here.
