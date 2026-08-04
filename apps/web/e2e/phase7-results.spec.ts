import { expect, test } from "@playwright/test";

test.describe.configure({ timeout: 120000 });

/**
 * Phase 7 focused E2E: pasted text → result → downloads → clear.
 * Deterministic; does not assert downloaded file contents with real PII.
 */
test("pasted text result downloads and clear", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Load fictional example/i }).click();
  await page.getByRole("button", { name: /^Analyze text$/i }).click();
  await expect(page.getByText(/Detections \(/i)).toBeVisible({ timeout: 90000 });
  await page.getByRole("button", { name: /Generate anonymized text/i }).click();
  await expect(page.getByText(/Anonymized preview/i)).toBeVisible({ timeout: 60000 });
  await expect(page.getByRole("button", { name: /Download .txt/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Download audit report/i })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /Download audit report/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("anonymization-audit-report.json");

  await page.getByRole("button", { name: /Clear current text/i }).click();
  await expect(page.getByText(/Anonymized preview/i)).toHaveCount(0);
});
