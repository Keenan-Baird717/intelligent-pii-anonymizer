import { expect, test } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

test.describe.configure({ timeout: 120000 });

function writeMinimalPdf(filePath: string) {
  // Minimal valid-enough PDF bytes for browser upload; API validates with PyMuPDF.
  const pdf = `%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer<< /Size 4 /Root 1 0 R >>
startxref
190
%%EOF
`;
  fs.writeFileSync(filePath, pdf, "utf8");
}

function writeDisguisedExe(filePath: string) {
  // PE signature with .pdf extension — should be rejected by the API.
  const buf = Buffer.alloc(64, 0);
  buf.write("MZ", 0, "ascii");
  fs.writeFileSync(filePath, buf);
}

test("pasted text review and anonymize flow", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /Load fictional example/i }).click();
  await page.getByRole("button", { name: /^Analyze text$/i }).click();

  await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 90000 });
  await expect(page.getByRole("button", { name: /^Reject$/i }).first()).toBeVisible();

  await page
    .getByRole("button", { name: /^Reject$/i })
    .first()
    .click();

  await page.getByLabel(/Default anonymization method/i).selectOption("replacement");
  await page.getByRole("button", { name: /Generate anonymized text/i }).click();

  await expect(page.getByText(/Anonymized preview/i)).toBeVisible({ timeout: 60000 });
  await expect(page.getByRole("button", { name: /Copy to clipboard/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Download .txt/i })).toBeVisible();

  const preview = page.locator("pre");
  await expect(preview).not.toBeEmpty();
});

test("valid fictional PDF upload, delete, and inaccessible job", async ({ page }) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pii-e2e-"));
  const pdfPath = path.join(dir, "fictional-upload.pdf");
  writeMinimalPdf(pdfPath);

  await page.goto("/");
  await page.getByRole("button", { name: /document upload/i }).click();
  await expect(page.getByRole("heading", { name: /document upload/i })).toBeVisible();

  await page.getByLabel(/browse files/i).setInputFiles(pdfPath);
  await expect(page.getByText(/fictional-upload\.pdf/i)).toBeVisible();
  await page.getByRole("button", { name: /upload document/i }).click();

  await expect(page.getByText(/upload accepted/i)).toBeVisible({ timeout: 60000 });
  await expect(page.getByText(/pending/i)).toBeVisible();
  await expect(page.getByText(/Job ID/i)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("storage_key");
  await expect(page.locator("body")).not.toContainText("/var/pii-uploads");

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: /delete now/i }).click();
  await expect(page.getByText(/job was deleted/i)).toBeVisible();
  await expect(page.getByText(/no longer accessible/i)).toBeVisible();

  try {
    fs.rmSync(dir, { recursive: true, force: true });
  } catch {
    // ignore Windows file lock during fixture cleanup
  }
});

test("invalid disguised file upload shows safe error", async ({ page }) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pii-e2e-bad-"));
  const badPath = path.join(dir, "fictional-disguise.pdf");
  writeDisguisedExe(badPath);

  try {
    await page.goto("/");
    await page.getByRole("button", { name: /document upload/i }).click();
    await page.getByLabel(/browse files/i).setInputFiles(badPath);
    await page.getByRole("button", { name: /upload document/i }).click();

    await expect(page.getByRole("alert")).toBeVisible({ timeout: 60000 });
    await expect(page.getByText(/Upload accepted/i)).toHaveCount(0);
  } finally {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      // Windows may briefly lock the uploaded fixture; ignore cleanup failures.
    }
  }
});
