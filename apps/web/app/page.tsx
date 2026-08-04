import { HealthStatus } from "@/components/HealthStatus";
import { HomeWorkspace } from "@/features/workspace/HomeWorkspace";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 sm:py-14">
      <header className="space-y-4 border-b border-slate-200 pb-8">
        <p className="text-sm font-semibold uppercase tracking-[0.12em] text-teal-800">
          Local privacy engineering demo
        </p>
        <h1 className="max-w-3xl text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Intelligent PII Anonymization Platform
        </h1>
        <p className="max-w-2xl text-base text-slate-600 sm:text-lg">
          Detect, review, and anonymize personally identifiable information in pasted text, PDFs,
          and images — with human-in-the-loop controls, true PDF redaction, local OCR, and immediate
          deletion.
        </p>
        <ul className="flex flex-wrap gap-2 text-xs text-slate-700" aria-label="Capability summary">
          <li className="status-badge bg-teal-50 text-teal-900 ring-1 ring-teal-200">
            Hybrid detection
          </li>
          <li className="status-badge bg-slate-100 text-slate-800 ring-1 ring-slate-200">
            Human review
          </li>
          <li className="status-badge bg-slate-100 text-slate-800 ring-1 ring-slate-200">
            True PDF redaction
          </li>
          <li className="status-badge bg-slate-100 text-slate-800 ring-1 ring-slate-200">
            Local OCR
          </li>
          <li className="status-badge bg-slate-100 text-slate-800 ring-1 ring-slate-200">
            Delete now
          </li>
        </ul>
      </header>

      <section aria-labelledby="health-heading" className="space-y-3">
        <h2 id="health-heading" className="text-lg font-semibold text-slate-900">
          System health
        </h2>
        <HealthStatus />
      </section>

      <HomeWorkspace />

      <section
        className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"
        role="note"
        aria-label="Demonstration warning"
      >
        <h2 className="font-semibold">Demonstration warning</h2>
        <p className="mt-1">
          This project is a demonstration tool. Automated PII detection can produce false positives
          or miss sensitive information. Users must review all results before sharing anonymized
          documents.
        </p>
        <p className="mt-2 text-amber-900/90">
          OCR accuracy varies for handwriting, low resolution, and complex layouts. Temporary
          uploads expire after 60 minutes and can be deleted immediately. This demo is not a
          compliance certification and does not claim HIPAA, GDPR, PIPEDA, SOC 2, or PCI compliance.
        </p>
      </section>
    </main>
  );
}
