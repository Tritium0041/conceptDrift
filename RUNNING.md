# ConceptDrift 运行文档

本文档说明如何在本地启动、配置、验证和排障 ConceptDrift。当前项目是前后端分离结构：

- 后端：`backend/`，Python 3.12 + FastAPI + SQLAlchemy + SQLite，使用 `uv` 管理依赖。
- 前端：`frontend/`，Next.js App Router + React + TypeScript + Tailwind CSS，使用 `npm` 管理依赖。
- 任务执行：FastAPI 进程内 `asyncio.Queue` worker，前端通过 SSE 获取任务状态。
- 默认 provider：`mock`，不需要 API key，可直接生成本地模拟报告。

## 1. 环境准备

确认本机有这些工具：

```bash
python3 --version
uv --version
node -v
npm -v
```

推荐版本：

- Python：`3.12`
- Node.js：`22` 或更高
- npm：`10` 或更高
- uv：任意较新版本

如果没有 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. 启动后端

打开一个终端：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
uv sync --dev
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动成功后，后端地址是：

```text
http://127.0.0.1:8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

默认返回类似：

```json
{"status":"ok","provider":"mock","database":"sqlite"}
```

后端第一次启动会自动创建数据库：

```text
backend/data/conceptdrift.sqlite3
```

启动时如果发现上次服务中断留下的 `pending` 或 `running` 任务，后端会把它们标记为失败，并显示“服务重启导致任务中断”。这些任务可以在前端或 API 中续跑。

## 3. 启动前端

再打开一个新终端：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

浏览器打开：

```text
http://127.0.0.1:3000
```

默认前端请求：

```text
http://127.0.0.1:8000
```

所以需要保持后端运行。

## 4. 配置文件

根目录 `.env.example` 是完整示例。实际本地运行时，建议按服务拆分：

- 后端变量放在 `backend/.env`。
- 前端变量放在 `frontend/.env.local`。

后端从 `backend/` 目录启动时会读取当前目录下的 `.env`。配置页默认也会写入 `backend/.env`。

最小后端配置：

```bash
CONCEPTDRIFT_DATABASE_URL=sqlite:///./data/conceptdrift.sqlite3
CONCEPTDRIFT_AGENT_PROVIDER=mock
CONCEPTDRIFT_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

前端连接其他后端地址时，在 `frontend/.env.local` 中设置：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## 5. Provider 模式

当前支持三种 provider：

| Provider | 说明 | 是否需要 `OPENAI_API_KEY` |
| :--- | :--- | :--- |
| `mock` | 本地确定性报告，适合开发、演示和测试 | 否 |
| `response` | 单次 OpenAI-compatible Responses API 调用 | 是 |
| `codex` | direct Codex threads 负责自动选题、来源调研、技术复核和最终汇总 | 是 |

### 使用配置页

打开：

```text
http://127.0.0.1:3000/settings
```

配置页可以修改：

- Provider：`mock`、`response`、`codex`
- OpenAI API key
- OpenAI Base URL
- Model
- OpenAI timeout
- OpenAI tracing disabled
- Codex agent timeout
- Codex network enabled
- Codex web search mode：`live`、`cached`、`disabled`

保存后，后端会更新内存中的 provider，并把配置写入 `backend/.env`。OpenAI key 是 write-only：接口不会明文回传，只返回是否已配置和 masked 值。

### 使用 `response` provider

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
export CONCEPTDRIFT_AGENT_PROVIDER=response
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-5
export OPENAI_BASE_URL=https://api.openai.com/v1
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`response` provider 会调用 `${OPENAI_BASE_URL}/responses`。如果 Base URL 以 `/v1` 结尾，会自动补成 `/v1/responses`。

### 使用 `codex` provider

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
export CONCEPTDRIFT_AGENT_PROVIDER=codex
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-5
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_TIMEOUT_SECONDS=90
export CONCEPTDRIFT_CODEX_AGENT_TIMEOUT_SECONDS=120
export CONCEPTDRIFT_CODEX_AGENT_NETWORK_ENABLED=true
export CONCEPTDRIFT_CODEX_AGENT_WEB_SEARCH_MODE=live
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`codex` provider 使用 `openai-agents` experimental Codex SDK direct thread 路径。GitHub、Hacker News、Product Hunt、Reddit 不由后端抓取 API 采集，而是作为 Codex 的公开调研目标。

Codex 线程当前配置：

- `sandbox_mode="read-only"`
- `approval_policy="never"`
- `skip_git_repo_check=True`
- `network_access_enabled` 由 `CONCEPTDRIFT_CODEX_AGENT_NETWORK_ENABLED` 控制
- `web_search_mode` 由 `CONCEPTDRIFT_CODEX_AGENT_WEB_SEARCH_MODE` 控制

## 6. 使用流程

### 定向模式

1. 打开工作台。
2. 选择“定向”。
3. 输入探索方向，例如 `AI code review assistant`。
4. 选择灵感来源和调研深度。
5. 点击“生成灵感报告”。

### YOLO 模式

1. 打开工作台。
2. 选择“YOLO”。
3. 选择灵感来源和调研深度。
4. 点击“YOLO 自动探索”。

YOLO 模式会先自动发现一个具体方向，再进入来源调研、技术复核和报告汇总。

命令行触发 YOLO：

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/generate \
  -H 'Content-Type: application/json' \
  -d '{"mode":"yolo","direction":"","sources":["github_trending","hackernews","product_hunt","last30days"],"depth":"standard"}'
```

可选：`last30days` 是 ConceptDrift 支持的 source，但 skill 本体需要使用者自行安装到 Codex，不随代码库提交或自动安装：

```bash
python3 "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo mvanhorn/last30days-skill \
  --path skills/last30days
```

安装后重启 Codex。使用 `codex` provider 并选择 `last30days` source 时，Codex 会调用用户本机的 `last30days` skill 调查近 30 天信号；未安装时，该来源只能返回需要安装 skill 的回退说明。

### 查看任务和报告

- 工作台左侧显示当前任务和最近任务。
- 任务执行时前端优先使用 SSE 订阅 `/api/tasks/{task_id}/events`；如果浏览器不支持 `EventSource`，会退回轮询。
- 任务成功后会生成报告，可在历史报告列表或详情页查看。
- 报告详情页支持 Markdown 和 PDF 导出。

### 续跑失败任务

前端失败任务会显示“续跑任务”按钮。也可以用 API：

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/<task_id>/resume
```

续跑会复用任务 checkpoint。`response` provider 会复用已保存的请求 payload 或模型输出；`codex` provider 会复用已完成的 YOLO 选题、来源调研、技术复核、同类产品侦查和最终汇总文本。

## 7. API

| Method | Path | 说明 |
| :--- | :--- | :--- |
| `GET` | `/api/health` | 健康检查，返回 provider 和数据库类型 |
| `GET` | `/api/config` | 读取运行配置，密钥只返回 masked 状态 |
| `PUT` | `/api/config` | 更新运行配置并写入 `.env` |
| `POST` | `/api/tasks/generate` | 创建生成任务 |
| `POST` | `/api/tasks/{task_id}/resume` | 续跑失败或中断任务 |
| `GET` | `/api/tasks` | 任务列表，支持 `status`、`limit`、`offset` |
| `GET` | `/api/tasks/{task_id}` | 任务详情 |
| `GET` | `/api/tasks/{task_id}/events` | SSE 任务事件 |
| `GET` | `/api/tasks/{task_id}/result` | 获取任务对应报告 |
| `GET` | `/api/reports` | 报告列表，支持 `q`、`limit`、`offset` |
| `GET` | `/api/reports/{report_id}` | 报告详情 |
| `GET` | `/api/reports/{report_id}/export?format=markdown|pdf` | 导出报告 |

创建定向任务：

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/generate \
  -H 'Content-Type: application/json' \
  -d '{"direction":"AI code review assistant","sources":["github_trending","hackernews"],"depth":"standard","mode":"guided"}'
```

查询最近任务：

```bash
curl 'http://127.0.0.1:8000/api/tasks?limit=8'
```

搜索报告：

```bash
curl 'http://127.0.0.1:8000/api/reports?q=CLI'
```

导出 Markdown：

```bash
curl -L 'http://127.0.0.1:8000/api/reports/<report_id>/export?format=markdown' -o report.md
```

导出 PDF：

```bash
curl -L 'http://127.0.0.1:8000/api/reports/<report_id>/export?format=pdf' -o report.pdf
```

## 8. 验证命令

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

## 9. 常见问题

### 前端页面打不开

确认前端 dev server 正在运行：

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

### 切换前端端口

例如改到 `3010`：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/frontend
npm run dev -- --hostname 127.0.0.1 --port 3010
```

如果后端 CORS 没有包含新前端地址，在 `backend/.env` 中更新：

```bash
CONCEPTDRIFT_CORS_ORIGINS=http://localhost:3010,http://127.0.0.1:3010
```

然后重启后端。

### 切换后端端口

例如改到 `8010`：

```bash
cd /Users/yuhaichuan/Documents/conceptDrift/backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

同时在 `frontend/.env.local` 中更新：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010
```

然后重启前端。

### 真实 provider 报错缺少 API key

`response` 和 `codex` 都需要：

```bash
OPENAI_API_KEY=sk-...
```

如果使用设置页保存 key，后端会写入 `backend/.env`。保存后新任务会立即使用新的 provider。

### 想清空本地数据

停止后端后删除 SQLite 文件：

```bash
rm /Users/yuhaichuan/Documents/conceptDrift/backend/data/conceptdrift.sqlite3
```

下次启动后端时会重新创建数据库。

## 10. 最短启动流程

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
