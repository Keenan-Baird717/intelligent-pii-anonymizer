"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchHealth, type HealthResponse } from "@/lib/api";

function statusLabel(health: HealthResponse): string {
  if (health.status === "ok" && health.database === "connected") {
    return "All systems operational";
  }
  if (health.database === "unavailable") {
    return "API running — database unavailable";
  }
  return "Degraded";
}

export function HealthStatus() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: false,
  });

  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="rounded-lg border p-4">
        Checking API health…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-800">
        Unable to reach the API health endpoint.
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <p className="text-sm font-medium text-slate-700">{statusLabel(data)}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm text-slate-600">
        <div>
          <dt className="font-medium">API status</dt>
          <dd>{data.status}</dd>
        </div>
        <div>
          <dt className="font-medium">Database</dt>
          <dd>{data.database}</dd>
        </div>
        <div>
          <dt className="font-medium">Version</dt>
          <dd>{data.version}</dd>
        </div>
      </dl>
    </div>
  );
}
