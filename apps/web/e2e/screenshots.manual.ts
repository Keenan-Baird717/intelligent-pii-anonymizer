/**
 * Explicit screenshot capture for portfolio docs (NOT part of ordinary CI).
 *
 * Prerequisites:
 * - Stack running at http://localhost:3000 and http://localhost:8000
 * - Fictional samples under samples/fictional/
 *
 * Run from apps/web:
 *   npm run screenshots
 */
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const ROOT = path.resolve(__dirname, "../../..");
const OUT = path.join(ROOT, "docs", "images");
const SAMPLES = path.join(ROOT, "samples", "fictional");

const VIEWPORT = { width: 1280, height: 800 };

test.beforeAll(() => {
  fs.mkdirSync(OUT, { recursive: true });
});

test.use({ viewport: VIEWPORT });

async function waitForHealthyHome(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Intelligent PII/i })).toBeVisible();
  await expect(page.getByText(/All systems operational|Degraded|Unable to reach/i)).toBeVisible({
    timeout: 60000,
  });
}

test.describe("portfolio screenshots (fictional data only)", () => {
  test("01 home input", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Load fictional example/i }).click();
    await page.screenshot({ path: path.join(OUT, "01-home-input.png"), fullPage: false });
  });

  test("02 pasted text detections", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Load fictional example/i }).click();
    await page.getByRole("button", { name: /^Analyze text$/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 60000 });
    await page.screenshot({
      path: path.join(OUT, "02-pasted-text-detection.png"),
      fullPage: false,
    });
  });

  test("03 human review workspace", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Load fictional example/i }).click();
    await page.getByRole("button", { name: /^Analyze text$/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 60000 });
    const reject = page.getByRole("button", { name: /^Reject$/i }).first();
    if (await reject.isVisible()) await reject.click();
    await page.screenshot({
      path: path.join(OUT, "03-human-review-workspace.png"),
      fullPage: false,
    });
  });

  test("04 text anonymization result", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Load fictional example/i }).click();
    await page.getByRole("button", { name: /^Analyze text$/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: /Accept visible/i }).click();
    await page.getByRole("button", { name: /Generate anonymized text/i }).click();
    await expect(page.getByText(/Anonymized preview/i)).toBeVisible({ timeout: 60000 });
    await page.screenshot({
      path: path.join(OUT, "04-text-anonymization-result.png"),
      fullPage: false,
    });
  });

  test("05 secure document upload", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Document upload/i }).click();
    await expect(page.getByRole("heading", { name: /Document upload/i })).toBeVisible();
    await page.screenshot({
      path: path.join(OUT, "05-secure-document-upload.png"),
      fullPage: false,
    });
  });

  test("06 pdf detection overlays", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Document upload/i }).click();
    await page
      .getByLabel(/browse files/i)
      .setInputFiles(path.join(SAMPLES, "fictional-text-document.pdf"));
    await page.getByRole("button", { name: /Upload document/i }).click();
    await page.getByRole("button", { name: /Open PDF review/i }).click();
    await page.getByRole("button", { name: /Analyze PDF/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 120000 });
    await page.screenshot({
      path: path.join(OUT, "06-pdf-detection-overlays.png"),
      fullPage: false,
    });
  });

  test("07 ocr image overlays", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Document upload/i }).click();
    await page
      .getByLabel(/browse files/i)
      .setInputFiles(path.join(SAMPLES, "fictional-id-card.png"));
    await page.getByRole("button", { name: /Upload document/i }).click();
    await page.getByRole("button", { name: /Open image review/i }).click();
    await page.getByRole("button", { name: /Analyze/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 120000 });
    await page.screenshot({ path: path.join(OUT, "07-ocr-image-overlays.png"), fullPage: false });
  });

  test("08 redacted result summary", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Document upload/i }).click();
    await page
      .getByLabel(/browse files/i)
      .setInputFiles(path.join(SAMPLES, "fictional-text-document.pdf"));
    await page.getByRole("button", { name: /Upload document/i }).click();
    await page.getByRole("button", { name: /Open PDF review/i }).click();
    await page.getByRole("button", { name: /Analyze PDF/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 120000 });
    const acceptButtons = page.getByRole("button", { name: /^Accept$/i });
    const n = await acceptButtons.count();
    for (let i = 0; i < n; i += 1) {
      await acceptButtons.nth(i).click();
    }
    await page.getByRole("button", { name: /Generate redacted PDF/i }).click();
    await expect(page.getByRole("heading", { name: /Processing complete/i })).toBeVisible({
      timeout: 120000,
    });
    await page.getByRole("heading", { name: /Processing complete/i }).scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(OUT, "08-redacted-result-summary.png"),
      fullPage: false,
    });
  });

  test("09 audit report summary", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Load fictional example/i }).click();
    await page.getByRole("button", { name: /^Analyze text$/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: /Accept visible/i }).click();
    await page.getByRole("button", { name: /Generate anonymized text/i }).click();
    await expect(page.getByRole("button", { name: /Download audit report/i })).toBeVisible();
    await page.screenshot({ path: path.join(OUT, "09-audit-report-summary.png"), fullPage: false });
  });

  test("10 delete now confirmation", async ({ page }) => {
    await waitForHealthyHome(page);
    await page.getByRole("button", { name: /Document upload/i }).click();
    await page
      .getByLabel(/browse files/i)
      .setInputFiles(path.join(SAMPLES, "fictional-text-document.pdf"));
    await page.getByRole("button", { name: /Upload document/i }).click();
    await expect(page.getByText(/Upload accepted/i)).toBeVisible({ timeout: 60000 });
    await expect(page.getByRole("button", { name: /Delete now/i })).toBeVisible();
    await page.screenshot({
      path: path.join(OUT, "10-delete-now-confirmation.png"),
      fullPage: false,
    });
  });
});
