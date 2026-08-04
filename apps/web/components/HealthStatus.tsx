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

function statusTone(health: HealthResponse): string {
  if (health.status === "ok" && health.database === "connected") {
    return "border-teal-200 bg-teal-50/60";
  }
  if (health.database === "unavailable") {
    return "border-amber-300 bg-amber-50";
  }
  return "border-amber-300 bg-amber-50";
}

export function HealthStatus() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: false,
  });

  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="panel p-4 text-sm text-slate-600">
        Checking API health…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-900">
        Unable to reach the API health endpoint.
      </div>
    );
  }

  const healthy = data.status === "ok" && data.database === "connected";

  return (
    <div role="status" aria-live="polite" className={`rounded-lg border p-4 ${statusTone(data)}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${
            healthy ? "bg-teal-700" : "bg-amber-600"
          }`}
          aria-hidden="true"
        />
        <p className="text-sm font-medium text-slate-800">{statusLabel(data)}</p>
        <span className="sr-only">{healthy ? "Healthy" : "Attention required"}</span>
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-sm text-slate-700 sm:grid-cols-3">
        <div>
          <dt className="font-medium text-slate-500">API status</dt>
          <dd>{data.status}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Database</dt>
          <dd>{data.database}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Version</dt>
          <dd className="break-all">{data.version}</dd>
        </div>
      </dl>
    </div>
  );
}
