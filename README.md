# ConceptDrift

ConceptDrift 是一个本地优先的开发者灵感生成器。它把一个产品方向或一个自动发现的机会点转成结构化调研任务，生成包含技术可行性、市场新颖性、商业潜力、来源信号和 MVP 建议的报告。

当前实现是前后端分离的本地 Web App：

- 后端：Python 3.12、FastAPI、SQLAlchemy、SQLite、进程内异步任务队列。
- 前端：Next.js App Router、React、TypeScript、Tailwind CSS。
- Provider：默认 `mock` 可离线生成确定性报告；`response` 调用 OpenAI-compatible Responses API；`codex` 通过 `openai-agents` experimental Codex SDK 启动 direct Codex research threads。
- 存储：任务、checkpoint、报告、来源条目都保存在本地 SQLite。

## 功能现状

- 定向生成：输入探索方向，选择来源和调研深度后生成报告。
- YOLO 模式：无需输入方向，由 agent 先自动发现一个值得研究的开发者产品机会。
- 来源选择：支持 `github_trending`、`hackernews`、`product_hunt`、`last30days`、`reddit`。
- 任务进度：后端任务异步执行，前端通过 SSE 实时显示状态和进度。
- 失败续跑：失败任务可通过 checkpoint 复用已完成阶段继续执行。
- 历史报告：支持列表、搜索、详情页、Markdown 导出和 PDF 导出。
- 运行配置：前端配置页可切换 provider、模型、Base URL、timeout、Codex 网络和 web search 设置，并写入 `backend/.env`。

## 目录结构

```text
.
├── backend/       # FastAPI API、任务队列、provider、SQLite 模型、Alembic、pytest
├── frontend/      # Next.js 工作台、配置页、报告详情页
├── README.md      # 项目总览
├── RUNNING.md     # 本地运行、配置、验证和排障
├── ConceptDrift 技术选型与架构设计文档.md
├── 产品需求文档 (PRD)：ConceptDrift — 开发者灵感生成器.md
└── .env.example   # 后端和前端环境变量示例
```

## 快速启动

后端：

```bash
cd backend
uv sync --dev
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

打开 [http://127.0.0.1:3000](http://127.0.0.1:3000)。默认后端地址是 [http://127.0.0.1:8000](http://127.0.0.1:8000)，默认 provider 是 `mock`，不需要 API key。

更完整的启动、配置和排障说明见 [RUNNING.md](RUNNING.md)。

## Provider

| Provider | 用途 | 是否需要 `OPENAI_API_KEY` |
| :--- | :--- | :--- |
| `mock` | 本地确定性报告，适合开发、演示和回归测试 | 否 |
| `response` | 单次 OpenAI-compatible Responses API 调用，适合验证模型连通性 | 是 |
| `codex` | direct Codex threads 负责 YOLO 选题、来源调研、技术复核和最终汇总 | 是 |

`codex` provider 不使用后端内置站点抓取器。GitHub、Hacker News、Product Hunt、Last30Days、Reddit 是 Codex 的调研目标，Codex 通过自己的浏览器、外部搜索、网络能力或用户自行安装的 `last30days` skill 检查公开页面并返回结构化信号。

### 可选：Last30Days Codex Skill

`last30days` 是应用里的可选调研源，但 skill 本体不提交到本代码库，也不由 ConceptDrift 自动安装。使用者如果希望 Codex 额外参考最近 30 天的 Reddit、X、YouTube、Hacker News、Polymarket、GitHub 和公开 Web 信号，需要自行安装 [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill)：

```bash
python3 "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo mvanhorn/last30days-skill \
  --path skills/last30days
```

安装后重启 Codex。使用 `codex` provider 生成报告并选择 `last30days` source 时，Codex 会尝试调用用户本机的 `last30days` skill；未安装时，该来源只能返回需要安装 skill 的回退说明。

可在前端 [http://127.0.0.1:3000/settings](http://127.0.0.1:3000/settings) 修改 provider 和模型配置。API key 不会被配置接口明文回传。

## API 概览

- `GET /api/health`
- `GET /api/config`
- `PUT /api/config`
- `POST /api/tasks/generate`
- `POST /api/tasks/{task_id}/resume`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/events`
- `GET /api/tasks/{task_id}/result`
- `GET /api/reports`
- `GET /api/reports/{report_id}`
- `GET /api/reports/{report_id}/export?format=markdown|pdf`

YOLO 请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/generate \
  -H 'Content-Type: application/json' \
  -d '{"mode":"yolo","direction":"","sources":["github_trending","hackernews","product_hunt","last30days"],"depth":"standard"}'
```

续跑失败任务：

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/<task_id>/resume
```

## 验证

```bash
cd backend && uv run pytest
cd frontend && npm run lint
cd frontend && npm run build
```

## 数据和配置

- 默认数据库：`backend/data/conceptdrift.sqlite3`。
- 后端运行配置：`backend/.env`，也可通过设置页写入。
- 前端后端地址：`frontend/.env.local` 中的 `NEXT_PUBLIC_API_BASE_URL`。
- 示例配置：根目录 `.env.example`。
