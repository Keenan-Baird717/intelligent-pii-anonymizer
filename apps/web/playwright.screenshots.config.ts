import { defineConfig, devices } from "@playwright/test";

/**
 * Separate config so screenshot capture is never part of `npm run test:e2e`.
 * Invoke explicitly:
 *   npx playwright test e2e/screenshots.manual.ts --config=playwright.screenshots.config.ts
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: /screenshots\.manual\.ts/,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results-screenshots",
  timeout: 180000,
  use: {
    baseURL: "http://localhost:3000",
    trace: "off",
    screenshot: "off",
    video: "off",
    ...devices["Desktop Chrome"],
  },
  projects: [{ name: "chromium" }],
});
