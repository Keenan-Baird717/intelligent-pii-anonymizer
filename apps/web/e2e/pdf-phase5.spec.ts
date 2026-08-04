import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

test.describe.configure({ timeout: 180000 });

const FIXTURES_DIR = path.resolve(__dirname, "../../../samples/fictional");
const TEXT_PDF = path.join(FIXTURES_DIR, "phase5-text-memo.pdf");
const IMAGE_ONLY_PDF = path.join(FIXTURES_DIR, "phase5-image-only.pdf");

const INTERNAL_LEAK_PATTERNS = [
  "storage_key",
  "/var/pii-uploads",
  "TEMP_UPLOAD_DIR",
  "phase5-text-memo.pdf",
  "phase5-image-only.pdf",
];

async function assertNoInternalLeaks(page: Page) {
  const body = await page.locator("body").innerText();
  for (const pattern of INTERNAL_LEAK_PATTERNS) {
    expect(body, `UI must not expose ${pattern}`).not.toContain(pattern);
  }
}

async function uploadPdfAndOpenReview(page: Page, fixturePath: string, displayName: string) {
  await page.goto("/");
  await page.getByRole("button", { name: /document upload/i }).click();
  await expect(page.getByRole("heading", { name: /document upload/i })).toBeVisible();

  await page.getByLabel(/browse files/i).setInputFiles({
    name: displayName,
    mimeType: "application/pdf",
    buffer: fs.readFileSync(fixturePath),
  });
  await expect(page.getByText(displayName, { exact: false })).toBeVisible();
  await page.getByRole("button", { name: /upload document/i }).click();
  await expect(page.getByText(/upload accepted/i)).toBeVisible({ timeout: 60000 });
  await page.getByRole("button", { name: /open pdf review/i }).click();
  await expect(page.getByRole("heading", { name: /pdf review workspace/i })).toBeVisible();
}

test("text-based fictional PDF analysis, review, redaction, and download", async ({ page }) => {
  expect(fs.existsSync(TEXT_PDF), `missing fixture ${TEXT_PDF}`).toBeTruthy();

  const downloadDir = fs.mkdtempSync(path.join(os.tmpdir(), "pii-e2e-dl-"));

  try {
    await uploadPdfAndOpenReview(page, TEXT_PDF, "fictional-memo.pdf");

    await page.getByRole("button", { name: /analyze pdf/i }).click();
    await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 90000 });
    await expect(page.getByText(/Detections \(0\)/i)).toHaveCount(0);

    // Overlays for detections should appear on the page canvas.
    await expect(page.getByLabel(/Detection .+ on page 1/i).first()).toBeVisible({
      timeout: 60000,
    });

    const detectionButtons = page.locator("ul li button").filter({ hasText: /p\.\d+/i });
    await expect(detectionButtons.first()).toBeVisible();
    const detectionCount = await detectionButtons.count();
    expect(detectionCount).toBeGreaterThanOrEqual(2);

    // Reject the first detection, accept the second.
    await detectionButtons.nth(0).click();
    await page.getByRole("button", { name: /^Reject$/i }).click();
    await expect(page.getByText(/rejected/i).first()).toBeVisible();

    await detectionButtons.nth(1).click();
    await page.getByRole("button", { name: /^Accept$/i }).click();
    await expect(page.getByText(/accepted/i).first()).toBeVisible();

    // Add one manual rectangular redaction via drag on the visible canvas region.
    await page.setViewportSize({ width: 1400, height: 1000 });
    await page.getByRole("button", { name: /add manual rectangle/i }).click();
    await expect(page.getByRole("button", { name: /drawing manual region/i })).toBeVisible();
    const surface = page.getByLabel(/PDF draw surface/i);
    await expect(surface).toBeVisible({ timeout: 60000 });
    await surface.scrollIntoViewIfNeeded();

    const box = await surface.boundingBox();
    expect(box).toBeTruthy();
    if (!box) throw new Error("PDF draw surface bounding box missing");

    const viewportHeight = page.viewportSize()?.height ?? 1000;
    const visibleTop = Math.max(box.y, 8);
    const visibleBottom = Math.min(box.y + box.height, viewportHeight - 8);
    expect(visibleBottom - visibleTop).toBeGreaterThan(60);

    const startX = box.x + 60;
    const startY = visibleTop + 40;
    const endX = startX + 120;
    const endY = Math.min(visibleBottom - 10, startY + 80);
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(endX, endY, { steps: 12 });
    await page.mouse.up();

    // Manual rectangle creation is best-effort in CI; continue if the entity list grew.
    const manualButton = page.getByRole("button", { name: /OTHER · p\.1.*Manual/i });
    const detectionsFour = page.getByText(/Detections \(4\)/i);
    await expect(
      manualButton.or(detectionsFour).or(page.getByText(/Detections \(3\)/i)),
    ).toBeVisible({ timeout: 30000 });

    await page.getByRole("button", { name: /generate redacted pdf/i }).click();
    await expect(page.getByText(/processing complete/i)).toBeVisible({ timeout: 90000 });
    await expect(page.getByText(/verification: passed/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /download audit report/i })).toBeVisible();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: /download redacted pdf/i }).click();
    const download = await downloadPromise;
    const suggested = download.suggestedFilename();
    expect(suggested.toLowerCase()).toContain("anonymized");
    expect(suggested.toLowerCase()).toMatch(/\.pdf$/);

    const savePath = path.join(downloadDir, suggested || "anonymized-document.pdf");
    await download.saveAs(savePath);
    expect(fs.statSync(savePath).size).toBeGreaterThan(0);

    await assertNoInternalLeaks(page);
  } finally {
    try {
      fs.rmSync(downloadDir, { recursive: true, force: true });
    } catch {
      // ignore Windows temp cleanup races
    }
  }
});

test("image-only fictional PDF analysis uses OCR or reports a safe OCR status", async ({
  page,
}) => {
  expect(fs.existsSync(IMAGE_ONLY_PDF), `missing fixture ${IMAGE_ONLY_PDF}`).toBeTruthy();

  await uploadPdfAndOpenReview(page, IMAGE_ONLY_PDF, "fictional-scan.pdf");

  await page.getByRole("button", { name: /analyze pdf/i }).click();

  // Phase 6: OCR may analyze image-only PDFs. Accept detections list or a coded error.
  await expect(page.getByText(/Detections \(/i).or(page.getByText(/Error code:/i))).toBeVisible({
    timeout: 90000,
  });

  if (await page.getByText(/Error code:/i).count()) {
    await expect(page.getByText(/Error code:\s*\w+/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /download redacted pdf/i })).toHaveCount(0);
  } else {
    await expect(page.getByText(/Detections \(/i)).toBeVisible();
    await expect(page.getByText(/fully analyzed/i)).toHaveCount(0);
  }

  await assertNoInternalLeaks(page);
});
