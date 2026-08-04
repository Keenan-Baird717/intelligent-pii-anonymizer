import { cleanup, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe, toHaveNoViolations } from "jest-axe";

import { HealthStatus } from "@/components/HealthStatus";
import { HomeWorkspace } from "@/features/workspace/HomeWorkspace";
import HomePage from "@/app/page";
import * as api from "@/lib/api";

expect.extend(toHaveNoViolations);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("accessibility smoke (axe)", () => {
  it("HomePage has no critical automated axe violations", async () => {
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      status: "ok",
      database: "connected",
      version: "0.1.0",
    });
    const { container } = renderWithClient(<HomePage />);
    const results = await axe(container, {
      rules: {
        // jsdom lacks full layout; region landmarks are covered by semantic main/sections.
        region: { enabled: false },
      },
    });
    expect(results).toHaveNoViolations();
  });

  it("HealthStatus and workspace chrome remain labeled", async () => {
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      status: "ok",
      database: "connected",
      version: "0.1.0",
    });
    const { container } = renderWithClient(
      <div>
        <HealthStatus />
        <HomeWorkspace />
      </div>,
    );
    const results = await axe(container, {
      rules: { region: { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });
});
