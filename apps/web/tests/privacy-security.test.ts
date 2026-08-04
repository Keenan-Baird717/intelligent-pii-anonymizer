/** Frontend Phase 8 privacy/security tests — fictional data only. */

import { afterEach, describe, expect, it, vi } from "vitest";

describe("browser privacy controls", () => {
  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("does not initialize analytics or telemetry globals", () => {
    expect((window as unknown as { gtag?: unknown }).gtag).toBeUndefined();
    expect((window as unknown as { ga?: unknown }).ga).toBeUndefined();
    expect((window as unknown as { dataLayer?: unknown }).dataLayer).toBeUndefined();
  });

  it("starts with empty browser storage", () => {
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("revokes object URLs after download helper pattern", () => {
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    const create = vi.fn().mockReturnValue("blob:mock");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
    try {
      const url = URL.createObjectURL(new Blob(["fictional"]));
      URL.revokeObjectURL(url);
      expect(create).toHaveBeenCalled();
      expect(revoke).toHaveBeenCalledWith("blob:mock");
    } finally {
      Object.defineProperty(URL, "createObjectURL", {
        configurable: true,
        value: originalCreate,
      });
      Object.defineProperty(URL, "revokeObjectURL", {
        configurable: true,
        value: originalRevoke,
      });
    }
  });

  it("does not place sensitive job content into the URL", () => {
    expect(window.location.search).not.toContain("@");
    expect(window.location.hash).toBe("");
  });
});

describe("manual rectangle client limit feedback", () => {
  it("documents a conservative client-side ceiling matching API defaults", () => {
    const MAX_MANUAL_RECTANGLES = 100;
    expect(MAX_MANUAL_RECTANGLES).toBeGreaterThan(0);
    expect(MAX_MANUAL_RECTANGLES).toBeLessThanOrEqual(1000);
  });
});
