"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { ArrowLeft, Download, ExternalLink, Loader2 } from "lucide-react";

import { Report, apiFetch, exportUrl } from "@/lib/api";
import { ScoreBar } from "@/components/ScoreBar";

export function ReportDetail({ reportId }: { reportId: number }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function loadReport() {
      try {
        const data = await apiFetch<Report>(`/api/reports/${reportId}`);
        if (alive) {
          setReport(data);
        }
      } catch (event) {
        if (alive) {
          setError(event instanceof Error ? event.message : "Failed to load report");
        }
      }
    }
    void loadReport();
    return () => {
      alive = false;
    };
  }, [reportId]);

  if (error) {
    return (
      <div className="rounded-lg border border-coral/20 bg-white p-6 text-coral shadow-soft">
        {error}
      </div>
    );
  }

  if (!report) {
    return (
      <div className="grid min-h-96 place-items-center rounded-lg border border-ink/10 bg-white shadow-soft">
        <div className="flex items-center gap-2 text-sm text-ink/60">
          <Loader2 className="animate-spin" size={18} aria-hidden="true" />
          正在加载报告
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
      <article className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft sm:p-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <Link href="/" className="inline-flex h-10 items-center gap-2 rounded-md border border-ink/10 px-3 text-sm font-medium text-ink/70 hover:text-moss">
            <ArrowLeft size={16} aria-hidden="true" />
            工作台
          </Link>
          <div className="flex gap-2">
            <a
              href={exportUrl(report.id, "markdown")}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-mist px-3 text-sm font-semibold text-ink"
            >
              <Download size={16} aria-hidden="true" />
              Markdown
            </a>
            <a
              href={exportUrl(report.id, "pdf")}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-3 text-sm font-semibold text-white"
            >
              <Download size={16} aria-hidden="true" />
              PDF
            </a>
          </div>
        </div>

        <div className="mb-6">
          <h1 className="text-2xl font-semibold leading-tight text-ink sm:text-3xl">{report.title}</h1>
          <p className="mt-3 text-sm leading-6 text-ink/65">{report.summary}</p>
        </div>

        <div className="prose prose-slate max-w-none prose-headings:text-ink prose-a:text-moss prose-strong:text-ink">
          <ReactMarkdown>{report.markdown}</ReactMarkdown>
        </div>
      </article>

      <aside className="space-y-5">
        <section className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
          <h2 className="mb-4 text-lg font-semibold text-ink">评分</h2>
          <div className="space-y-4">
            {Object.entries(report.scores).map(([name, value]) => (
              <ScoreBar key={name} name={name} value={value} />
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
          <h2 className="mb-4 text-lg font-semibold text-ink">标签</h2>
          <div className="flex flex-wrap gap-2">
            {report.tags.map((tag) => (
              <span key={tag} className="rounded bg-mist px-2 py-1 text-xs text-ink/65">
                {tag}
              </span>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
          <h2 className="mb-4 text-lg font-semibold text-ink">来源</h2>
          <div className="space-y-3">
            {report.sources.map((source) => (
              <a
                key={source.id}
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-md border border-ink/10 p-3 transition hover:border-moss/40"
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <span className="text-sm font-semibold text-ink">{source.source}</span>
                  <ExternalLink className="shrink-0 text-ink/40" size={15} aria-hidden="true" />
                </div>
                <div className="text-sm font-medium leading-5 text-moss">{source.title}</div>
                <p className="mt-2 text-xs leading-5 text-ink/60">{source.summary}</p>
                <div className="mt-2 text-xs text-ink/50">信号分 {source.signal_score}</div>
              </a>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

