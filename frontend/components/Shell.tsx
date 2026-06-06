import Link from "next/link";
import { BrainCircuit, Settings } from "lucide-react";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 pb-4">
        <Link href="/" className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-ink text-white">
            <BrainCircuit size={20} aria-hidden="true" />
          </span>
          <span>
            <span className="block text-lg font-semibold leading-tight">ConceptDrift</span>
            <span className="block text-sm text-ink/60">开发者灵感生成器</span>
          </span>
        </Link>
        <nav className="flex items-center gap-2">
          <Link
            href="/"
            className="rounded-md border border-ink/10 bg-white px-3 py-2 text-sm font-medium text-ink/70 shadow-soft hover:border-moss/40 hover:text-moss"
          >
            工作台
          </Link>
          <Link
            href="/settings"
            className="inline-flex items-center gap-2 rounded-md border border-ink/10 bg-white px-3 py-2 text-sm font-medium text-ink/70 shadow-soft hover:border-moss/40 hover:text-moss"
          >
            <Settings size={15} aria-hidden="true" />
            配置
          </Link>
        </nav>
      </header>
      {children}
    </main>
  );
}
