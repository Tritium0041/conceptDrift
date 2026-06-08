# ConceptDrift 技术选型与架构设计文档

本文档按当前仓库实现整理，覆盖 `backend/`、`frontend/`、provider、任务队列、数据模型和后续扩展边界。

## 1. 当前技术栈

| 模块 | 当前选型 | 说明 |
| :--- | :--- | :--- |
| 前端 | Next.js App Router + React + TypeScript + Tailwind CSS | 提供工作台、配置页、报告详情页和 Markdown 渲染。 |
| 后端 API | FastAPI + Pydantic + SQLAlchemy | 提供任务、报告、配置、导出和健康检查 API。 |
| 本地存储 | SQLite | 默认路径为 `backend/data/conceptdrift.sqlite3`，适合本地优先 MVP。 |
| 任务执行 | 进程内 `asyncio.Queue` worker | 创建任务后立即返回 `task_id`，后台 worker 异步生成报告。 |
| 实时进度 | Server-Sent Events | 前端优先订阅 `/api/tasks/{task_id}/events`，必要时退回轮询。 |
| 报告导出 | Markdown + ReportLab PDF | Markdown 直接导出，PDF 使用 `STSong-Light` 字体渲染中文。 |
| Provider | `mock`、`response`、`codex` | 默认 mock；真实模型路径使用 OpenAI-compatible API 或 direct Codex threads。 |
| 依赖管理 | 后端 `uv`，前端 `npm` | 后端要求 Python 3.12，前端使用 Next.js 16 / React 19。 |
| 测试 | pytest、ESLint、Next build | 后端覆盖 API、provider、checkpoint、SSE、导出和来源工具。 |

当前实现不依赖 PostgreSQL、Redis、Celery 或 WebSocket。它们可以作为未来多用户/多进程部署时的扩展方向，但不是当前本地 MVP 的运行前提。

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────────┐
│                    Next.js Frontend                     │
│ 工作台 / 配置页 / 报告详情 / SSE 任务进度 / 导出入口       │
└───────────────────────────┬─────────────────────────────┘
                            │ REST + SSE
┌───────────────────────────▼─────────────────────────────┐
│                    FastAPI Backend                       │
│ /api/tasks /api/reports /api/config /api/health          │
└───────────────┬──────────────────────┬──────────────────┘
                │                      │
                │                      ▼
                │              SQLite persistence
                │              tasks / reports / source_items
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│                 In-process TaskQueue                     │
│ pending task -> provider.generate -> report persistence  │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│                     Providers                            │
│ mock / response / codex                                  │
└─────────────────────────────────────────────────────────┘
```

设计目标是把当前 MVP 保持在“本地可跑、依赖少、可验证”的范围内，同时保留清晰边界，后续可以把 SQLite 换成 PostgreSQL，把进程内队列换成外部队列。

## 3. 后端启动生命周期

后端入口在 `backend/app/main.py`。`create_app()` 会完成以下初始化：

1. 读取 `Settings`，包括数据库、CORS、provider、OpenAI 和 Codex 配置。
2. 创建 SQLAlchemy engine 和 session factory。
3. 根据 `CONCEPTDRIFT_AGENT_PROVIDER` 构建 provider。
4. 创建 `TaskQueue`。
5. FastAPI lifespan 启动时初始化数据库表。
6. 标记上次服务中断留下的 `pending` / `running` 任务为失败。
7. 启动进程内 worker。
8. 服务关闭时取消 worker。

SQLite schema 同时有 Alembic migration 文件和运行时兼容逻辑。`init_database()` 会执行 `Base.metadata.create_all()`，并为旧 SQLite 数据库补齐 `tasks.mode` 和 `tasks.checkpoint` 字段。

## 4. 数据模型

当前核心表有三张：

| 表 | 模型 | 作用 |
| :--- | :--- | :--- |
| `tasks` | `Task` | 记录生成请求、来源、深度、模式、状态、进度、错误、checkpoint 和关联报告。 |
| `reports` | `Report` | 保存报告标题、摘要、Markdown、评分、标签、归档状态和时间戳。 |
| `source_items` | `SourceItem` | 保存每份报告引用的来源信号、URL、摘要和信号分。 |

任务状态：

- `pending`：已创建，等待 worker 执行。
- `running`：worker 正在调用 provider。
- `succeeded`：报告已生成并入库。
- `failed`：任务失败或服务重启中断，可续跑。

任务模式：

- `guided`：围绕用户输入的 `direction` 生成报告。
- `yolo`：先自动发现方向，再生成报告。

## 5. 任务执行流程

```text
POST /api/tasks/generate
        │
        ▼
create_task() 写入 tasks 表，返回 task_id
        │
        ▼
TaskQueue.enqueue(task_id)
        │
        ▼
TaskQueue.process(task_id)
        │
        ▼
provider.generate(request, progress)
        │
        ├── progress(value, stage) 更新任务进度
        ├── progress.save_checkpoint(patch) 保存可续跑 checkpoint
        ▼
GeneratedReport 写入 reports + source_items
        │
        ▼
task.status = succeeded, progress = 100, report_id = ...
```

失败时，worker 会把任务标记为：

```text
status = failed
stage = 任务失败，可续跑
error = 异常信息
```

`POST /api/tasks/{task_id}/resume` 会把失败任务重新置为 `pending` 并重新入队。provider 会从 `task.checkpoint` 读取已完成阶段，避免重复昂贵步骤。

## 6. Provider 架构

所有 provider 都实现同一个接口：

```python
async def generate(
    request: GenerateTaskRequest,
    progress: ProgressCallback,
) -> GeneratedReport:
    ...
```

输出统一为：

- `title`
- `summary`
- `markdown`
- `scores`
- `tags`
- `sources`

### 6.1 `mock`

`MockInspirationProvider` 是默认 provider：

- 不需要网络和 API key。
- 根据输入方向、来源和深度生成确定性报告。
- 支持 `guided` 和 `yolo`。
- 适合本地开发、演示和回归测试。

### 6.2 `response`

`OpenAIResponsesProvider` 使用 OpenAI-compatible Responses API：

- 需要 `OPENAI_API_KEY`。
- 默认 Base URL 是 `https://api.openai.com/v1`。
- 自动把 Base URL 规范化到 `/responses`。
- 使用 JSON schema 要求模型返回固定报告结构。
- 会 clamp 评分到 `0-100`，并去重 tags。
- checkpoint 会保存请求 payload 和模型输出文本，续跑时可跳过重复 API 调用。

### 6.3 `codex`

`OpenAIAgentsProvider` 是当前的 Codex provider 名称。实际执行路径是 `openai-agents` 包里的 experimental Codex SDK direct threads，当前不会调用后端站点抓取 API。

Codex provider 的主要阶段：

1. 启动 Codex 调研与编排。
2. YOLO 模式下先运行 “Codex YOLO direction discovery agent” 自动发现方向。
3. 对用户选择的来源并发运行 “Codex source research agent”。
4. 并行运行技术可行性复核 prompt 和 “Codex competitor landscape agent”。
5. 运行最终 “Codex Orchestrator Agent” prompt，输出符合 JSON schema 的报告。
6. 校验结构并写入数据库。

来源当前包括：

- GitHub Trending：`https://github.com/trending`
- Hacker News：`https://news.ycombinator.com`
- Product Hunt：`https://www.producthunt.com`
- Reddit：`https://www.reddit.com/r/programming`

这些来源是 Codex 的公开调研目标。Codex 自己使用可用的浏览器、外部搜索或网络工具检查公开页面，后端只负责构造 prompt、校验输出、保存结果。

Codex thread 当前安全设置：

- `sandbox_mode="read-only"`
- `approval_policy="never"`
- `skip_git_repo_check=True`
- `network_access_enabled` 可配置
- `web_search_mode` 可配置为 `disabled`、`cached` 或 `live`

`AgentsSdkRuntime` 适配器仍保留在代码中，但当前 `codex` provider 的测试明确锁定了 direct Codex research runtime 路径。

## 7. 前端架构

前端入口：

- `/`：工作台，包含生成表单、任务队列、历史报告列表和搜索。
- `/settings`：运行配置页。
- `/reports/[id]`：报告详情页。

核心组件：

| 组件 | 作用 |
| :--- | :--- |
| `Shell` | 页面外壳和导航。 |
| `Workspace` | 生成任务、订阅进度、展示最近任务和报告列表。 |
| `SettingsPanel` | 读取和更新后端 provider 配置。 |
| `ReportDetail` | 渲染 Markdown 报告、评分、标签、来源和导出按钮。 |
| `ScoreBar` | 统一展示评分。 |

前端 API 封装在 `frontend/lib/api.ts`：

- `API_BASE_URL` 默认 `http://127.0.0.1:8000`。
- 可通过 `NEXT_PUBLIC_API_BASE_URL` 覆盖。
- `taskEventsUrl()` 构造 SSE URL。
- `exportUrl()` 构造 Markdown / PDF 导出 URL。

## 8. 配置架构

后端配置在 `backend/app/config.py`：

| 字段 | 环境变量 | 默认值 |
| :--- | :--- | :--- |
| `database_url` | `CONCEPTDRIFT_DATABASE_URL` | `sqlite:///./data/conceptdrift.sqlite3` |
| `agent_provider` | `CONCEPTDRIFT_AGENT_PROVIDER` | `mock` |
| `cors_origins` | `CONCEPTDRIFT_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |
| `openai_api_key` | `OPENAI_API_KEY` | 空 |
| `openai_base_url` | `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| `openai_model` | `OPENAI_MODEL` | `gpt-5` |
| `openai_timeout_seconds` | `OPENAI_TIMEOUT_SECONDS` | `90` |
| `openai_tracing_disabled` | `CONCEPTDRIFT_OPENAI_TRACING_DISABLED` | `true` |
| `codex_agent_timeout_seconds` | `CONCEPTDRIFT_CODEX_AGENT_TIMEOUT_SECONDS` | `120` |
| `codex_agent_network_enabled` | `CONCEPTDRIFT_CODEX_AGENT_NETWORK_ENABLED` | `true` |
| `codex_agent_web_search_mode` | `CONCEPTDRIFT_CODEX_AGENT_WEB_SEARCH_MODE` | `live` |
| `config_env_path` | `CONCEPTDRIFT_CONFIG_ENV_PATH` | `.env` |

`PUT /api/config` 会：

1. 校验 provider 和字段范围。
2. 构建新 provider，提前发现不支持的 provider 名称。
3. 写入 `.env`。
4. 更新内存中的 settings。
5. 更新 `TaskQueue` 使用的 provider。

API key 不会在响应中明文返回，只返回 `openai_api_key_configured` 和 `openai_api_key_masked`。

## 9. API 边界

当前 API 保持 REST + SSE：

- 任务写入和续跑使用 POST。
- 任务与报告查询使用 GET。
- 配置读取和更新使用 GET / PUT。
- 任务进度使用 SSE。
- 报告导出使用普通文件响应。

没有用户系统、权限系统、团队协作、多租户隔离或远程任务队列。当前默认部署假设是本地单用户开发环境。

## 10. 已知扩展方向

当项目从本地 MVP 走向长期服务时，建议优先考虑：

1. 把 SQLite 替换为 PostgreSQL，保留 SQLAlchemy 模型边界。
2. 把进程内 `asyncio.Queue` 替换为 Redis/RQ、Celery 或其他持久队列。
3. 增加任务取消、重试次数、超时策略和更细粒度的 checkpoint 可视化。
4. 为报告增加收藏、归档切换、标签筛选和二次追问。
5. 为真实 provider 增加成本、耗时、调用日志和错误分类。
6. 增加部署文档、生产环境 CORS、密钥管理和备份策略。

这些扩展不改变当前 MVP 的核心原则：前端只负责操作体验，后端负责任务状态和持久化，provider 负责调研与报告生成。
