# 产品需求文档 (PRD)：ConceptDrift - 开发者灵感生成器

本文档按当前仓库实现更新，描述 ConceptDrift 现阶段产品目标、已实现能力、非目标和后续优先级。

## 1. 产品概述

- 产品名称：ConceptDrift
- 产品定位：本地优先的开发者灵感生成器。
- 核心目标：帮助个人开发者从一个方向或一个自动发现的机会点出发，快速获得可执行的项目灵感调研报告。
- 目标用户：个人开发者、独立开发者、开源维护者、技术创作者。

ConceptDrift 当前不是通用趋势门户，也不是团队协作平台。它更像一个本地工作台：提交方向、选择信号源、等待 agent 调研、查看和导出报告。

## 2. 当前 MVP 状态

当前已实现一个可本地运行的 Web App：

- 后端：FastAPI + SQLite + 进程内异步 worker。
- 前端：Next.js 工作台、配置页、报告详情页。
- 默认 provider：`mock`，无需 API key。
- 真实 provider：`response` 和 `codex`。
- 报告持久化：任务、报告、来源条目和 checkpoint 保存在 SQLite。

## 3. 核心用户场景

### 3.1 定向探索

用户输入一个方向，例如 `AI code review assistant`，选择来源和调研深度，系统生成报告。

当前支持：

- 输入方向，最长 300 字符。
- 来源选择：GitHub Trending、Hacker News、Product Hunt、Reddit。
- 深度选择：Quick、Standard、Deep。
- 报告包含摘要、核心概念、技术可行性、市场新颖性、商业潜力、灵感来源和 MVP 建议。

### 3.2 YOLO 自动探索

用户不提供明确方向，系统自动发现一个值得研究的开发者产品机会。

当前支持：

- 工作台选择 YOLO 模式。
- API 使用 `mode="yolo"`。
- `mock` provider 返回固定自动探索方向。
- `response` provider 在单次模型调用中自主选择方向。
- `codex` provider 先运行 YOLO direction discovery，再进入来源调研和报告汇总。

### 3.3 任务进度与续跑

用户提交任务后，系统异步执行并展示进度。

当前支持：

- 创建任务后立即返回 `task_id`。
- 工作台展示当前任务和最近任务。
- 前端通过 SSE 订阅任务事件。
- 任务失败后可以续跑。
- checkpoint 复用已完成阶段，降低重复调用成本。
- 服务重启导致的中断任务会被标记为失败，可续跑。

### 3.4 报告管理与导出

用户可以查看历史报告并导出。

当前支持：

- 历史报告列表。
- 按标题或摘要搜索。
- 报告详情页 Markdown 渲染。
- 评分、标签、来源信号展示。
- Markdown 导出。
- PDF 导出。

### 3.5 运行配置

用户可以在前端配置真实 provider。

当前支持：

- 切换 `mock`、`response`、`codex`。
- 配置 OpenAI API key、Base URL、model、timeout。
- 配置 Codex agent timeout、网络开关、web search mode。
- 配置保存到 `backend/.env`。
- API key 不明文回传，只显示 masked 状态。

## 4. Provider 需求边界

### `mock`

需求目标：

- 无外部依赖。
- 输出稳定，便于开发和测试。
- 支持 guided 和 yolo。

当前状态：已实现。

### `response`

需求目标：

- 使用 OpenAI-compatible Responses API。
- 返回符合固定 JSON schema 的报告。
- 支持 provider API 错误提示。
- 支持续跑时复用已保存的 payload 或 output text。

当前状态：已实现。

### `codex`

需求目标：

- 使用 direct Codex threads 做公开信号调研。
- 不依赖后端内置 GitHub/HN/Product Hunt/Reddit 抓取 API。
- 支持 YOLO 方向发现、来源并发调研、技术可行性复核和最终报告汇总。
- 通过 JSON schema 约束结构化输出。
- 支持 checkpoint 续跑。

当前状态：已实现基础链路。

## 5. API 需求

当前 API First 边界已经实现：

- 健康检查：`GET /api/health`
- 配置：`GET /api/config`、`PUT /api/config`
- 创建任务：`POST /api/tasks/generate`
- 续跑任务：`POST /api/tasks/{task_id}/resume`
- 任务列表：`GET /api/tasks`
- 任务详情：`GET /api/tasks/{task_id}`
- 任务事件：`GET /api/tasks/{task_id}/events`
- 任务结果：`GET /api/tasks/{task_id}/result`
- 报告列表：`GET /api/reports`
- 报告详情：`GET /api/reports/{report_id}`
- 报告导出：`GET /api/reports/{report_id}/export?format=markdown|pdf`

## 6. 非目标

当前版本不包含：

- 多用户登录和权限系统。
- 团队协作、评论、审批。
- 邮件、短信或定时推送。
- 云端部署和生产运维能力。
- 远程持久任务队列。
- 复杂的报告编辑器。
- 计费、额度和成本管理。

这些能力可以作为后续产品方向，但不是当前本地 MVP 的验收范围。

## 7. 成功标准

当前 MVP 的成功标准：

1. 用户能在本地用两条命令分别启动后端和前端。
2. 无 API key 时，`mock` provider 能稳定生成报告。
3. 配置 API key 后，用户能切换到 `response` 或 `codex` provider。
4. 任务状态能在前端持续更新。
5. 失败任务能续跑，并复用 checkpoint。
6. 历史报告能搜索、查看，并导出 Markdown / PDF。
7. 后端测试、前端 lint、前端 build 能作为基础回归验证。

## 8. 后续优先级

建议下一步按价值排序：

1. 增加任务取消、重试次数和超时原因分类。
2. 增加报告收藏、归档切换、标签筛选和更清晰的报告状态。
3. 增加 provider 调用耗时、成本和错误日志展示。
4. 增加更完整的部署文档和生产配置示例。
5. 将任务队列迁移到外部持久队列，支持多进程后端。
6. 将数据库迁移到 PostgreSQL，支持更长期的数据保留和扩展。
7. 增加二次追问或基于报告生成 MVP checklist 的工作流。
