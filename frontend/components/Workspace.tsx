"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Download, FileText, RefreshCcw, Search, Sparkles } from "lucide-react";

import {
  API_BASE_URL,
  Health,
  ReportList,
  ReportListItem,
  Task,
  TaskMode,
  TaskList,
  apiFetch,
  exportUrl,
  resumeTask,
  taskEventsUrl
} from "@/lib/api";
import { ScoreBar } from "@/components/ScoreBar";

const SOURCE_OPTIONS = [
  { id: "github_trending", label: "GitHub" },
  { id: "hackernews", label: "Hacker News" },
  { id: "product_hunt", label: "Product Hunt" },
  { id: "last30days", label: "Last30Days" },
  { id: "reddit", label: "Reddit" }
];

const DEPTH_OPTIONS = [
  { id: "quick", label: "Quick" },
  { id: "standard", label: "Standard" },
  { id: "deep", label: "Deep" }
] as const;

const MODE_OPTIONS: Array<{ id: TaskMode; label: string }> = [
  { id: "guided", label: "定向" },
  { id: "yolo", label: "YOLO" }
];

type Depth = (typeof DEPTH_OPTIONS)[number]["id"];

export function Workspace() {
  const [direction, setDirection] = useState("AI code review assistant");
  const [mode, setMode] = useState<TaskMode>("guided");
  const [sources, setSources] = useState<string[]>(["github_trending", "hackernews", "product_hunt", "last30days"]);
  const [depth, setDepth] = useState<Depth>("standard");
  const [task, setTask] = useState<Task | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [query, setQuery] = useState("");
  const [loadingReports, setLoadingReports] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [provider, setProvider] = useState<string>("agent");
  const [error, setError] = useState<string | null>(null);

  const selectedSources = useMemo(
    () => SOURCE_OPTIONS.filter((source) => sources.includes(source.id)).map((source) => source.label),
    [sources]
  );

  const upsertTask = useCallback((nextTask: Task) => {
    setTask((current) => (current?.id === nextTask.id ? nextTask : current));
    setTasks((current) => {
      const withoutTask = current.filter((item) => item.id !== nextTask.id);
      return [nextTask, ...withoutTask].sort(
        (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)
      );
    });
  }, []);

  const loadReports = useCallback(async () => {
    setLoadingReports(true);
    setError(null);
    try {
      const params = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
      const data = await apiFetch<ReportList>(`/api/reports${params}`);
      setReports(data.items);
    } catch (event) {
      setError(event instanceof Error ? event.message : "Failed to load reports");
    } finally {
      setLoadingReports(false);
    }
  }, [query]);

  const loadTasks = useCallback(async () => {
    try {
      const data = await apiFetch<TaskList>("/api/tasks?limit=8");
      setTasks(data.items);
      const activeTask = data.items.find((item) => item.status === "running" || item.status === "pending");
      setTask(activeTask ?? data.items[0] ?? null);
    } catch (event) {
      setError(event instanceof Error ? event.message : "Failed to load tasks");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadReports();
      void loadTasks();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadReports, loadTasks]);

  useEffect(() => {
    let active = true;
    void apiFetch<Health>("/api/health")
      .then((payload) => {
        if (active) {
          setProvider(payload.provider);
        }
      })
      .catch(() => {
        if (active) {
          setProvider("agent");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const activeTaskId = task && task.status !== "succeeded" && task.status !== "failed" ? task.id : null;

  useEffect(() => {
    if (!activeTaskId) {
      return;
    }
    if (typeof EventSource === "undefined") {
      const timer = window.setInterval(async () => {
        try {
          const nextTask = await apiFetch<Task>(`/api/tasks/${activeTaskId}`);
          upsertTask(nextTask);
          if (nextTask.status === "succeeded") {
            void loadReports();
          }
        } catch (event) {
          setError(event instanceof Error ? event.message : "Failed to refresh task");
        }
      }, 900);
      return () => window.clearInterval(timer);
    }

    const events = new EventSource(taskEventsUrl(activeTaskId));
    events.addEventListener("task", (event) => {
      const nextTask = JSON.parse(event.data) as Task;
      upsertTask(nextTask);
      if (nextTask.status === "succeeded") {
        void loadReports();
      }
    });
    events.addEventListener("done", () => {
      events.close();
    });
    events.addEventListener("error", () => {
      events.close();
    });
    return () => events.close();
  }, [activeTaskId, loadReports, upsertTask]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const nextTask = await apiFetch<Task>("/api/tasks/generate", {
        method: "POST",
        body: JSON.stringify({ direction: mode === "yolo" ? "" : direction, sources, depth, mode })
      });
      upsertTask(nextTask);
    } catch (event) {
      setError(event instanceof Error ? event.message : "Failed to create task");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResumeTask(taskId: string) {
    setResuming(true);
    setError(null);
    try {
      const nextTask = await resumeTask(taskId);
      upsertTask(nextTask);
    } catch (event) {
      setError(event instanceof Error ? event.message : "Failed to resume task");
    } finally {
      setResuming(false);
    }
  }

  function toggleSource(source: string) {
    setSources((current) => {
      if (current.includes(source)) {
        return current.length === 1 ? current : current.filter((item) => item !== source);
      }
      return [...current, source];
    });
  }

  return (
    <div className="grid flex-1 gap-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(420px,1.05fr)]">
      <section className="flex flex-col gap-5">
        <div className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
          <div className="mb-5 flex items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-ink sm:text-3xl">
                灵感生成工作台
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-ink/65">
                输入方向，选择信号源，生成一份包含技术可行性、市场新颖性和商业潜力的报告。
              </p>
            </div>
            <span className="rounded-md bg-mist px-3 py-2 text-sm font-medium text-moss">
              Agent: {provider}
            </span>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <span className="mb-2 block text-sm font-medium text-ink">探索模式</span>
              <div className="grid grid-cols-2 rounded-md border border-ink/10 bg-mist p-1">
                {MODE_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setMode(option.id)}
                    className={`h-10 rounded px-3 text-sm font-medium transition ${
                      mode === option.id ? "bg-white text-ink shadow-sm" : "text-ink/60 hover:text-ink"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {mode === "guided" ? (
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-ink">探索方向</span>
                <textarea
                  className="min-h-28 w-full resize-y rounded-md border border-ink/15 bg-white px-3 py-3 text-base outline-none transition focus:border-moss focus:ring-2 focus:ring-moss/15"
                  value={direction}
                  onChange={(event) => setDirection(event.target.value)}
                  maxLength={300}
                />
              </label>
            ) : null}

            <div>
              <span className="mb-2 block text-sm font-medium text-ink">灵感来源</span>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                {SOURCE_OPTIONS.map((source) => {
                  const active = sources.includes(source.id);
                  return (
                    <button
                      key={source.id}
                      type="button"
                      onClick={() => toggleSource(source.id)}
                      className={`h-11 rounded-md border text-sm font-medium transition ${
                        active
                          ? "border-moss bg-moss text-white"
                          : "border-ink/10 bg-white text-ink/70 hover:border-moss/50"
                      }`}
                    >
                      {source.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <span className="mb-2 block text-sm font-medium text-ink">调研深度</span>
              <div className="grid grid-cols-3 rounded-md border border-ink/10 bg-mist p-1">
                {DEPTH_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setDepth(option.id)}
                    className={`h-10 rounded px-3 text-sm font-medium transition ${
                      depth === option.id ? "bg-white text-ink shadow-sm" : "text-ink/60 hover:text-ink"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-md bg-ink px-4 font-semibold text-white transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Sparkles size={18} aria-hidden="true" />
              {submitting ? "正在提交" : mode === "yolo" ? "YOLO 自动探索" : "生成灵感报告"}
            </button>
          </form>
        </div>

        <div className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-ink">任务队列</h2>
            {task ? <span className="text-sm uppercase text-ink/55">{task.status}</span> : null}
          </div>
          {task ? (
            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="text-ink/70">{task.direction}</span>
                  <span className="tabular-nums text-ink/60">{task.progress}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-ink/10">
                  <div className="h-full rounded-full bg-coral" style={{ width: `${task.progress}%` }} />
                </div>
              </div>
              <div className="text-sm leading-6 text-ink/65">
                {task.stage} · 模式：{task.mode === "yolo" ? "YOLO" : "定向"} · 来源：{task.sources.join(" / ")} · 深度：
                {task.depth}
              </div>
              {task.error ? <div className="rounded-md bg-coral/10 p-3 text-sm text-coral">{task.error}</div> : null}
              {task.status === "failed" ? (
                <button
                  type="button"
                  onClick={() => void handleResumeTask(task.id)}
                  disabled={resuming}
                  className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-white transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <RefreshCcw size={16} aria-hidden="true" />
                  {resuming ? "正在续跑" : "续跑任务"}
                </button>
              ) : null}
              {task.report_id ? (
                <Link
                  href={`/reports/${task.report_id}`}
                  className="inline-flex h-10 items-center gap-2 rounded-md bg-moss px-4 text-sm font-semibold text-white"
                >
                  查看报告
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
              ) : null}

              <div className="border-t border-ink/10 pt-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium text-ink">最近任务</span>
                  <button
                    type="button"
                    onClick={() => void loadTasks()}
                    className="text-xs font-medium text-moss"
                  >
                    刷新
                  </button>
                </div>
                <div className="space-y-2">
                  {tasks.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setTask(item)}
                      className={`grid w-full gap-1 rounded-md border px-3 py-2 text-left transition ${
                        task.id === item.id
                          ? "border-moss bg-mist"
                          : "border-ink/10 bg-white hover:border-moss/40"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <span className="truncate font-medium text-ink">{item.direction}</span>
                        <span className="shrink-0 uppercase text-ink/50">{item.status}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3 text-xs text-ink/55">
                        <span className="truncate">{item.stage}</span>
                        <span className="tabular-nums">{item.progress}%</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm leading-6 text-ink/60">提交任务后，这里会持久显示任务进度，刷新页面也会恢复。</p>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-ink">历史报告</h2>
            <p className="mt-1 text-sm text-ink/60">保存在本地 SQLite 数据库中。</p>
          </div>
          <button
            type="button"
            onClick={() => void loadReports()}
            className="inline-flex h-10 items-center gap-2 rounded-md border border-ink/10 px-3 text-sm font-medium text-ink/70 hover:border-moss/50 hover:text-moss"
            title="刷新"
          >
            <RefreshCcw size={16} aria-hidden="true" />
            刷新
          </button>
        </div>

        <form
          className="mb-4 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void loadReports();
          }}
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={16} />
            <input
              className="h-11 w-full rounded-md border border-ink/10 bg-white pl-9 pr-3 text-sm outline-none focus:border-moss focus:ring-2 focus:ring-moss/15"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索标题或摘要"
            />
          </div>
          <button className="h-11 rounded-md bg-mist px-4 text-sm font-semibold text-ink" type="submit">
            搜索
          </button>
        </form>

        {error ? <div className="mb-4 rounded-md bg-coral/10 p-3 text-sm text-coral">{error}</div> : null}
        {loadingReports ? <div className="py-8 text-center text-sm text-ink/50">正在加载报告</div> : null}
        {!loadingReports && reports.length === 0 ? (
          <div className="rounded-md border border-dashed border-ink/15 p-8 text-center text-sm text-ink/55">
            暂无报告
          </div>
        ) : null}

        <div className="space-y-3">
          {reports.map((report) => (
            <article key={report.id} className="rounded-md border border-ink/10 p-4 transition hover:border-moss/40">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <Link href={`/reports/${report.id}`} className="font-semibold text-ink hover:text-moss">
                    {report.title}
                  </Link>
                  <p className="mt-2 line-clamp-2 text-sm leading-6 text-ink/65">{report.summary}</p>
                </div>
                <FileText className="mt-1 shrink-0 text-moss" size={19} aria-hidden="true" />
              </div>
              <div className="mb-3 grid gap-3">
                {Object.entries(report.scores).map(([name, value]) => (
                  <ScoreBar key={name} name={name} value={value} />
                ))}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-2">
                  {report.tags.slice(0, 4).map((tag) => (
                    <span key={tag} className="rounded bg-mist px-2 py-1 text-xs text-ink/65">
                      {tag}
                    </span>
                  ))}
                </div>
                <a
                  href={exportUrl(report.id, "markdown")}
                  className="inline-flex items-center gap-1 text-sm font-medium text-moss"
                >
                  <Download size={15} aria-hidden="true" />
                  Markdown
                </a>
              </div>
            </article>
          ))}
        </div>
        <div className="mt-5 rounded-md bg-mist p-3 text-xs leading-5 text-ink/55">
          API endpoint: {API_BASE_URL}
        </div>
      </section>
    </div>
  );
}
