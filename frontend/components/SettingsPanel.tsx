"use client";

import { FormEvent, useEffect, useState } from "react";
import { Check, KeyRound, Save, ServerCog } from "lucide-react";

import { AppConfig, AppConfigUpdate, ProviderName, apiFetch } from "@/lib/api";

const PROVIDER_OPTIONS: Array<{ value: ProviderName; label: string }> = [
  { value: "mock", label: "mock" },
  { value: "codex", label: "codex" },
  { value: "response", label: "response" }
];

export function SettingsPanel() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void apiFetch<AppConfig>("/api/config")
      .then((payload) => {
        if (active) {
          setConfig(payload);
        }
      })
      .catch((event) => {
        if (active) {
          setError(event instanceof Error ? event.message : "Failed to load config");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!config) {
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    const payload: AppConfigUpdate = {
      agent_provider: config.agent_provider,
      openai_api_key: apiKey,
      clear_openai_api_key: clearApiKey,
      openai_base_url: config.openai_base_url,
      openai_model: config.openai_model,
      openai_timeout_seconds: config.openai_timeout_seconds,
      openai_tracing_disabled: config.openai_tracing_disabled,
      codex_agent_timeout_seconds: config.codex_agent_timeout_seconds,
      codex_agent_network_enabled: config.codex_agent_network_enabled,
      codex_agent_web_search_mode: config.codex_agent_web_search_mode
    };
    try {
      const nextConfig = await apiFetch<AppConfig>("/api/config", {
        method: "PUT",
        body: JSON.stringify(payload)
      });
      setConfig(nextConfig);
      setApiKey("");
      setClearApiKey(false);
      setMessage("配置已保存");
    } catch (event) {
      setError(event instanceof Error ? event.message : "Failed to save config");
    } finally {
      setSaving(false);
    }
  }

  function updateConfig<K extends keyof AppConfig>(key: K, value: AppConfig[K]) {
    setConfig((current) => (current ? { ...current, [key]: value } : current));
  }

  if (loading) {
    return <div className="rounded-lg border border-ink/10 bg-white p-6 text-sm text-ink/60 shadow-soft">正在加载配置</div>;
  }

  if (!config) {
    return <div className="rounded-lg border border-coral/20 bg-white p-6 text-sm text-coral shadow-soft">{error}</div>;
  }

  return (
    <form className="grid gap-5" onSubmit={handleSubmit}>
      <section className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-ink text-white">
            <ServerCog size={19} aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold text-ink">运行配置</h1>
            <p className="mt-1 text-sm text-ink/60">当前 provider：{config.agent_provider}</p>
          </div>
        </div>

        {message ? (
          <div className="mb-4 inline-flex items-center gap-2 rounded-md bg-moss/10 px-3 py-2 text-sm text-moss">
            <Check size={15} aria-hidden="true" />
            {message}
          </div>
        ) : null}
        {error ? <div className="mb-4 rounded-md bg-coral/10 p-3 text-sm text-coral">{error}</div> : null}

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-ink">Provider</span>
            <select
              className="h-11 w-full rounded-md border border-ink/15 bg-white px-3 text-sm outline-none focus:border-moss focus:ring-2 focus:ring-moss/15"
              value={config.agent_provider}
              onChange={(event) => updateConfig("agent_provider", event.target.value as ProviderName)}
            >
              {PROVIDER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-ink">Model</span>
            <input
              className="h-11 w-full rounded-md border border-ink/15 bg-white px-3 text-sm outline-none focus:border-moss focus:ring-2 focus:ring-moss/15"
              value={config.openai_model}
              onChange={(event) => updateConfig("openai_model", event.target.value)}
            />
          </label>

          <label className="block md:col-span-2">
            <span className="mb-2 block text-sm font-medium text-ink">Base URL</span>
            <input
              className="h-11 w-full rounded-md border border-ink/15 bg-white px-3 text-sm outline-none focus:border-moss focus:ring-2 focus:ring-moss/15"
              value={config.openai_base_url}
              onChange={(event) => updateConfig("openai_base_url", event.target.value)}
            />
          </label>
        </div>
      </section>

      <section className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
        <div className="mb-4 flex items-center gap-2">
          <KeyRound size={18} className="text-moss" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-ink">OpenAI Key</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-ink">API Key</span>
            <input
              className="h-11 w-full rounded-md border border-ink/15 bg-white px-3 text-sm outline-none focus:border-moss focus:ring-2 focus:ring-moss/15"
              type="password"
              value={apiKey}
              placeholder={config.openai_api_key_masked ?? "sk-..."}
              onChange={(event) => setApiKey(event.target.value)}
              disabled={clearApiKey}
            />
          </label>
          <label className="flex items-end gap-2 pb-3 text-sm text-ink/70">
            <input
              className="h-4 w-4 accent-moss"
              type="checkbox"
              checked={clearApiKey}
              onChange={(event) => setClearApiKey(event.target.checked)}
            />
            清空当前 key
          </label>
        </div>
        <div className="mt-3 text-sm text-ink/60">
          状态：{config.openai_api_key_configured ? config.openai_api_key_masked : "未配置"}
        </div>
      </section>

      <section className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
        <h2 className="mb-4 text-lg font-semibold text-ink">运行参数</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <NumberField
            label="OpenAI Timeout"
            value={config.openai_timeout_seconds}
            onChange={(value) => updateConfig("openai_timeout_seconds", value)}
          />
          <NumberField
            label="Codex Agent Timeout"
            value={config.codex_agent_timeout_seconds}
            onChange={(value) => updateConfig("codex_agent_timeout_seconds", value)}
          />
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-ink">Web Search Mode</span>
            <select
              className="h-11 w-full rounded-md border border-ink/15 bg-white px-3 text-sm outline-none focus:border-moss focus:ring-2 focus:ring-moss/15"
              value={config.codex_agent_web_search_mode}
              onChange={(event) => updateConfig("codex_agent_web_search_mode", event.target.value)}
            >
              <option value="live">live</option>
              <option value="cached">cached</option>
              <option value="disabled">disabled</option>
            </select>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-4">
          <Toggle
            label="Tracing Disabled"
            checked={config.openai_tracing_disabled}
            onChange={(checked) => updateConfig("openai_tracing_disabled", checked)}
          />
          <Toggle
            label="Codex Network"
            checked={config.codex_agent_network_enabled}
            onChange={(checked) => updateConfig("codex_agent_network_enabled", checked)}
          />
        </div>
      </section>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex h-11 items-center gap-2 rounded-md bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save size={16} aria-hidden="true" />
          {saving ? "保存中" : "保存配置"}
        </button>
      </div>
    </form>
  );
}

function NumberField({
  label,
  value,
  onChange
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-ink">{label}</span>
      <input
        className="h-11 w-full rounded-md border border-ink/15 bg-white px-3 text-sm outline-none focus:border-moss focus:ring-2 focus:ring-moss/15"
        type="number"
        min={1}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function Toggle({
  label,
  checked,
  onChange
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-ink/70">
      <input
        className="h-4 w-4 accent-moss"
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}
