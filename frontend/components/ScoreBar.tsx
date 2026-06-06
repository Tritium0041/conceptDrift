const LABELS: Record<string, string> = {
  technical_feasibility: "技术可行性",
  market_novelty: "市场新颖性",
  business_potential: "商业潜力"
};

export function ScoreBar({ name, value }: { name: string; value: number }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-ink">{LABELS[name] ?? name}</span>
        <span className="tabular-nums text-ink/70">{value}/100</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-ink/10">
        <div
          className="h-full rounded-full bg-moss"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

