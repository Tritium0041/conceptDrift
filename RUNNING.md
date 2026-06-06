# ConceptDrift 运行文档

本文档说明如何在本地把 ConceptDrift 跑起来。项目是前后端分离结构：

- 后端：`backend/`，Python 3.12 + FastAPI + SQLite，使用 `uv` 管理依赖。
- 前端：`frontend/`，Next.js + TypeScript + Tailwind CSS，使用 `npm` 管理依赖。
- 默认 Agent Provider 是 `mock`，不需要配置 API Key 就可以生成模拟报告；也可以切换到 OpenAI Agents SDK 或 direct Codex agent provider。

## 1. 环境准备

先确认本机有这些工具：

```bash
python3 --version
uv --version
node -v
npm -v
```

推荐版本：

- Python：`3.12` 或更高
- Node.js：`22` 或更高
- npm：`10` 或更高
- uv：任意较新版本

如果没有 `uv`，可以安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. 启动后端

打开一个终端，进入后端目录：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
uv sync --dev
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动成功后，后端地址是：

```text
http://127.0.0.1:8000
```

可以用健康检查确认：

```bash
curl http://127.0.0.1:8000/api/health
```

正常返回：

```json
{"status":"ok","provider":"mock","database":"sqlite"}
```

后端第一次启动时会自动创建 SQLite 数据库：

```text
backend/data/conceptdrift.sqlite3
```

## 3. 启动前端

再打开一个新的终端，进入前端目录：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

启动成功后，浏览器打开：

```text
http://127.0.0.1:3000
```

默认前端会请求：

```text
http://127.0.0.1:8000
```

所以需要先保持后端运行。

## 4. 环境变量

默认情况下不用配置环境变量，项目会用 mock provider 和本地 SQLite。

也可以打开前端配置页：

```text
http://127.0.0.1:3000/settings
```

配置页保存后会写入 `backend/.env`，并让后续新任务立即使用新 provider。OpenAI key 不会被接口明文回传，页面只显示 masked 值。

如果需要自定义后端配置，可以在 `backend/.env` 中设置：

```bash
CONCEPTDRIFT_DATABASE_URL=sqlite:///./data/conceptdrift.sqlite3
CONCEPTDRIFT_AGENT_PROVIDER=mock
CONCEPTDRIFT_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

使用 Codex provider 时，把 provider 改成 `codex`，并设置 API Key：

```bash
CONCEPTDRIFT_AGENT_PROVIDER=codex
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_TIMEOUT_SECONDS=90
CONCEPTDRIFT_CODEX_AGENT_TIMEOUT_SECONDS=120
CONCEPTDRIFT_CODEX_AGENT_NETWORK_ENABLED=true
CONCEPTDRIFT_CODEX_AGENT_WEB_SEARCH_MODE=live
```

Provider 模式：

- `mock`：本地模拟报告，不需要 API Key。
- `codex`：OpenAI Agents SDK 编排 + direct Codex agent 调研。后端不再调用 GitHub、Hacker News、Product Hunt、Reddit 的现成抓取 API；每个来源由 Codex agent 自己通过浏览器/外部搜索/网络工具调研并返回结构化信号，再由 Orchestrator Agent 汇总结构化报告。
- `response`：轻量单次 Responses API provider，用于调试 OpenAI-compatible API 连通性或快速生成。

Codex agent 可选配置：

```bash
CONCEPTDRIFT_CODEX_AGENT_TIMEOUT_SECONDS=120
CONCEPTDRIFT_CODEX_AGENT_NETWORK_ENABLED=true
CONCEPTDRIFT_CODEX_AGENT_WEB_SEARCH_MODE=live
```

未设置 `OPENAI_API_KEY` 时，所有真实 OpenAI provider 都会失败并返回明确错误。

密钥说明：

- OpenAI 只需要 `OPENAI_API_KEY`，不是 AK/SK 成对配置。
- Codex agent 调研走 `openai-agents` 的 experimental Codex SDK direct thread 路径。
- GitHub、Hacker News、Product Hunt、Reddit 不再由后端公开接口抓取，而是作为 Codex 调研目标。

如果前端要连接其他后端地址，可以在 `frontend/.env.local` 中设置：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

根目录的 `.env.example` 是配置示例。因为后端和前端分别从各自目录启动，实际本地运行时建议把对应变量放到 `backend/.env` 或 `frontend/.env.local`。

## 5. 验证命令

后端测试：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
uv run pytest
```

前端 lint：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm run lint
```

前端生产构建：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm run build
```

本地已经验证通过的结果：

- `uv run pytest`：`22 passed`
- `npm run lint`：通过
- `npm run build`：通过，Next.js 构建成功

## 6. 常见问题

### 前端页面打不开

确认前端 dev server 还在运行：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

然后访问：

```text
http://127.0.0.1:3000
```

### 前端提示接口请求失败

先确认后端是否启动：

```bash
curl http://127.0.0.1:8000/api/health
```

如果返回正常，再确认 `frontend/.env.local` 中的 `NEXT_PUBLIC_API_BASE_URL` 是否指向同一个后端地址。

### 端口被占用

后端换端口，例如 `8010`：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

同时更新前端环境变量：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010
```

前端换端口，例如 `3010`：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm run dev -- --hostname 127.0.0.1 --port 3010
```

如果后端 CORS 没有包含新前端地址，需要在 `backend/.env` 里更新：

```bash
CONCEPTDRIFT_CORS_ORIGINS=http://localhost:3010,http://127.0.0.1:3010
```

然后重启后端。

### 想清空本地数据

停止后端后删除 SQLite 文件：

```bash
rm /Users/yuhaichuan/Documents/conceptDrift/backend/data/conceptdrift.sqlite3
```

下次启动后端时会重新创建数据库。

## 7. 最短启动流程

后端终端：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
uv sync --dev
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端终端：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

浏览器打开：

```text
http://127.0.0.1:3000
```
