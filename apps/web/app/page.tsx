import { HealthStatus } from "@/components/HealthStatus";
import { HomeWorkspace } from "@/features/workspace/HomeWorkspace";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-10 px-6 py-16">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Portfolio project
        </p>
        <h1 className="text-4xl font-bold tracking-tight">
          Intelligent PII Anonymization Platform
        </h1>
        <p className="text-lg text-slate-600">
          Phase 5: pasted-text anonymization plus text-based PDF analysis with true redaction.
          Scanned/image OCR is not enabled yet.
        </p>
      </header>

      <section aria-labelledby="health-heading">
        <h2 id="health-heading" className="mb-3 text-xl font-semibold">
          System health
        </h2>
        <HealthStatus />
      </section>

      <HomeWorkspace />

      <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p>
          This project is a demonstration tool. Automated PII detection can produce false positives
          or miss sensitive information. Users must review all results before sharing anonymized
          documents.
        </p>
      </section>
    </main>
  );
}
