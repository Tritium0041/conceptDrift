# ConceptDrift 技术选型与架构设计文档

**作者**：Manus AI

本文档基于《开发者灵感生成器产品需求文档 (PRD)》，结合业界最新的 Agent Native 架构设计模式以及对 `openai-codex` 库和 OpenAI Agents SDK 的深度调研，为项目提供详细的技术选型与架构设计方案。

---

## 1. 核心技术栈概览

为实现一个真正的 Agent Native 项目，我们将整个系统划分为三大核心部分：前端交互层、后端 API 服务层以及 Agent 编排引擎层。

| 模块 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| **前端 (Web App)** | Next.js (React) + Tailwind CSS | 提供极客友好的响应式界面，支持服务端渲染 (SSR) 和 Markdown 报告的高效渲染。 |
| **后端 API 服务** | FastAPI (Python) + PostgreSQL + Redis | FastAPI 擅长处理异步请求，与 Python 原生的 Agent 生态完美契合；Redis 用于 Celery 任务队列，处理耗时的灵感生成任务。 |
| **中心编排 Agent** | OpenAI Agents SDK (Python) | 官方提供的多 Agent 编排框架，作为系统的唯一大脑，负责任务规划、指令下发和结果汇总 [1]。 |
| **执行 Agent (调研/复核)** | `openai-agents` experimental Codex SDK | 外部信号调研和技术可行性复核由独立 Codex 线程承担，Codex 自己调用浏览器/外部搜索/网络工具，不经过后端站点抓取 API。 |

---

## 2. Agent Native 架构设计

### 2.1 核心设计哲学：一个大脑，多个 Codex 工作者

本系统采用"中心编排 + Codex 执行"的清晰分层架构。中心编排 Agent 是系统的唯一决策者，它不执行具体的信息检索工作；后端把每个来源调研任务拆成独立 prompt，直接交给 Codex 线程执行。这种设计的优势在于：Codex 天然具备联网搜索、代码执行和长文本生成能力，无需额外开发专项站点抓取器，且每个 Codex 实例可以在独立只读沙盒中并发运行，互不干扰。

```
用户请求
    │
    ▼
┌─────────────────────────────────────┐
│      中心编排 Agent (Orchestrator)   │  ← OpenAI Agents SDK
│  - 任务拆解与规划                    │
│  - 向 Codex 下发子任务指令            │
│  - 聚合各 Codex 返回结果              │
│  - 生成最终报告结构                   │
└──────────────┬──────────────────────┘
               │ Direct Codex SDK threads
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│Codex #1│ │Codex #2│ │Codex #3│  ← experimental Codex SDK
│灵感采集 │ │技术调研 │ │市场调研 │
│(联网)  │ │(联网+  │ │(联网)  │
│        │ │ 代码验证)│        │
└────────┘ └────────┘ └────────┘
```

### 2.2 中心编排 Agent 的职责边界

中心编排 Agent 的职责被严格限定，它只做三件事：

第一，**任务规划**：接收用户请求（手动触发或定时触发），生成一份结构化的子任务清单，例如"采集本周 HackerNews 高赞技术帖"、"验证该技术方向的 GitHub 生态成熟度"、"分析 Product Hunt 上的竞品分布"。

第二，**任务分发**：后端通过 direct Codex runtime 并发启动多个 Codex 线程，给每个线程传入来源、探索方向、输出 JSON schema 和调研约束。Codex 自己使用可用的浏览器/外部搜索/网络能力完成调研。

第三，**结果聚合**：收集所有 Codex 实例的返回结果，按照预设的报告模板（技术可行性 + 市场新颖性 + 商业潜力参考）进行结构化整合，输出最终的 Markdown 报告。

### 2.3 Codex 实例的工作范围

所有具体的"脏活累活"均由 Codex 实例承担，包括但不限于：

| 子任务类型 | Codex 执行内容 | 沙盒模式 |
| :--- | :--- | :--- |
| 灵感采集 | 使用 Codex 自己的浏览器/外部搜索/网络工具调研 HackerNews、Reddit、GitHub Trending、Product Hunt 等平台的最新内容，提炼创意方向 | `read-only` |
| 技术可行性调研 | 搜索特定技术栈的文档、社区活跃度、依赖成熟度，形成工程风险与测试策略建议 | `read-only` |
| 市场新颖性分析 | 搜索 App Store、Product Hunt、GitHub 等平台，检索是否存在类似产品，分析竞品差异化空间 | `read-only` |
| 报告撰写 | 根据编排 Agent 提供的结构化数据，撰写完整的 Markdown 格式调研报告 | `read-only` |

---

## 3. Codex direct runtime 的集成方案

### 3.1 安装与启动

本项目使用 `openai-agents` 已包含的 experimental Codex SDK 路径直接启动 Codex 线程。

```python
from agents.extensions.experimental.codex import Codex, CodexOptions, ThreadOptions, TurnOptions

codex = Codex(CodexOptions(api_key=openai_api_key, base_url=openai_base_url))
thread = codex.start_thread(
    ThreadOptions(
        model="gpt-5",
        sandbox_mode="read-only",
        skip_git_repo_check=True,
        network_access_enabled=True,
        web_search_mode="live",
        approval_policy="never",
    )
)
turn = await thread.run(prompt, TurnOptions(output_schema=source_schema, idle_timeout_seconds=120))
```

### 3.2 中心编排 Agent 调用 Codex 的代码示例

```python
import asyncio
from agents import Agent, Runner

async def run_inspiration_pipeline(user_request: str) -> str:
    source_snapshots = await run_codex_source_research(user_request)
    technical_review = await run_codex_technical_review(user_request, source_snapshots)
    orchestrator = Agent(
        name="Orchestrator",
        model="gpt-5",
        instructions="综合 Codex 调研结果，输出符合 JSON schema 的灵感报告。",
    )
    result = await Runner.run(
        orchestrator,
        {
            "request": user_request,
            "source_snapshots": source_snapshots,
            "technical_review": technical_review,
        },
    )
    return result.final_output

# 调用示例
report = asyncio.run(run_inspiration_pipeline("帮我生成一个面向开发者的 SaaS 工具创意"))
print(report)
```

---

## 4. 后端服务与异步任务架构

由于 Agent 调研和报告生成是一个长耗时过程（通常需要数十秒至数分钟），必须采用异步任务架构，避免 HTTP 请求超时。

整体流程如下：用户在前端触发"生成灵感"请求，FastAPI 接收后立即返回一个 `task_id`，并将任务推送至 Redis 队列；Celery Worker 消费任务，启动上述的 Orchestrator + Codex 工作流；前端通过 WebSocket 或轮询 API，实时获取 Agent 的执行状态（如"Codex 正在检索 HackerNews..."），并在任务完成后拉取完整报告。

```
前端 → POST /api/tasks/generate
         │
         ▼
     FastAPI 返回 { task_id: "xxx" }
         │
         ▼
     Celery Worker 消费任务
         │
         ▼
     Orchestrator Agent 启动
         │
         ▼
     Codex direct runtime 执行子任务（可并发）
         │
         ▼
     报告写入 PostgreSQL
         │
         ▼
前端 ← GET /api/tasks/{task_id}/result
```

---

## 5. 关键技术点与注意事项

**沙盒安全性**：Codex 具备代码执行能力，必须确保其在受限沙盒中运行。当前外部调研与技术复核统一使用 `read-only` 模式，并将 approval policy 固定为 `never`，防止意外的文件系统修改 [3]。

**Tracing 与可观测性**：多 Codex 实例并发执行时，调试难度较高。应启用 OpenAI Agents SDK 内置的 Tracing 功能，记录每一次 LLM 调用和工具执行的完整链路，便于定位问题和优化提示词 [1]。

**定时任务**：每日自动生成灵感的功能，推荐使用 Celery Beat 作为定时调度器，配置 Cron 表达式触发任务，无需引入额外的调度中间件。

---

## 6. 总结

本方案的核心设计理念是**职责极简化**：中心编排 Agent 只做决策，Codex 只做执行。这种分层使得系统逻辑清晰、易于维护，同时充分发挥了 Codex 在联网搜索、代码执行和长文本生成方面的综合能力，真正实现了"Agent 深度参与决策、启发与调研"的 Agent Native 设计目标。

---

### References
[1] [OpenAI Agents SDK Python: Tools](https://openai.github.io/openai-agents-python/tools/)
[2] [OpenAI Codex Docs: Use Codex with the Agents SDK](https://developers.openai.com/codex/guides/agents-sdk)
[3] [OpenAI: The next evolution of the Agents SDK](https://openai.com/index/the-next-evolution-of-the-agents-sdk/)
