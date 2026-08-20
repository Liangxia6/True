# TrueEval Deep Research 工作流框架技术设计 V0.1

> 状态：Draft  
> 日期：2026-08-19  
> 适用阶段：Research MVP（R0–R2）  
> 目标读者：后端工程师、评测工程师、平台工程师、技术负责人

## 1. 文档目的

本文定义 TrueEval Deep Research 评测工作流框架的技术方案、开发要求、开发流程与验收标准。

该框架用于统一执行和评估 Deep Research API、网页产品及人工导入结果，重点解决以下问题：

- 不同 Benchmark 与不同被测产品之间的 N×M 接入复杂度；
- 长时间异步任务的轮询、限流、超时、重试和断点恢复；
- 原始请求、响应、搜索结果、报告、引用和评分结果的完整留存；
- 被测产品执行失败与答案质量错误的分离；
- 不重新调用被测产品即可替换 Grader 并重新评分；
- 对成本、延迟、成功率、结果质量和引用质量进行统一统计。

本文是实现约束，不是产品使用说明。具体 Benchmark 数据格式继续遵循《TrueEval Research MVP Benchmark 数据格式 V0.1》。

## 2. 范围与非目标

### 2.1 本期范围

Research MVP 包含：

1. 加载并冻结 Benchmark、split 和任务快照；
2. 接入同步或异步 Research Agent API；
3. 支持冻结 SOP 后的人工结果导入；
4. 将不同产品输出归一化为统一 Research Answer Artifact；
5. 执行官方 Grader、TrueEval 引用 Grader 和可选 LLM Judge；
6. 保存运行状态、事件、证据、用量和评分结果；
7. 支持失败恢复、离线重评分和报告重建；
8. 提供 CLI 作为首个操作入口。

### 2.2 非目标

本期不包含：

- 使用 TrueEval 自行实现通用 Deep Research Agent；
- 为普通 LLM 自动提供搜索、规划和报告生成能力；
- 使用 LangGraph 编排评测运行；
- 大规模网页自动化和桌面自动化；
- 跨 Research、Coding、Productivity 等领域计算统一总分；
- 面向外部用户的多租户控制台；
- 分布式调度集群和跨区域容灾。

如果未来由 TrueEval 提供搜索和研究编排，被测对象必须标记为“模型 + TrueEval Research Agent”，不得只使用底层模型名称。

## 3. 核心架构决策

### 3.1 不使用 LangGraph

TrueEval 的主流程是确定性的评测编排：

```text
冻结任务 → 调用被测产品 → 等待结果 → 保存证据
→ 归一化 → 评分 → 验证 → 聚合 → 发布
```

步骤、状态转换、重试条件和失败分类必须由代码明确控制，不应由模型动态决定。因此 MVP 不使用 LangGraph。

LangGraph 只适用于以下独立场景：

- 被测对象本身是由 TrueEval 团队开发的 Research Agent；
- Agent 内部需要模型驱动的规划、搜索和工具调用；
- 该 Agent 作为 SUT 通过标准 `SUTAdapter` 接入评测框架。

### 3.2 MVP 技术栈

- 语言：Python 3.12；
- 数据模型与校验：Pydantic 2；
- 异步并发：`asyncio`；
- 状态数据库：SQLite；
- Artifact 存储：本地文件系统；
- 配置文件：YAML；
- 命令行：Typer；
- HTTP：HTTPX；
- 测试：pytest、pytest-asyncio；
- 数据迁移：显式版本迁移脚本；
- 日志：Python logging，输出结构化 JSONL。

依赖必须通过 `pyproject.toml` 声明并锁定。生产代码不得依赖 Benchmark upstream 目录中的临时运行环境。

### 3.3 后续扩展

满足以下任一条件后，再评估 Temporal：

- 单次 Run 超过 1,000 个任务；
- 需要多进程或多节点 Worker；
- 长任务需要跨部署版本可靠恢复；
- SQLite 写入成为瓶颈；
- 需要定时运行、任务优先级和集中式运维。

迁移时只替换 Scheduler/Runner 层。Adapter、Schema、Artifact、Grader 和报告层不得依赖 Temporal SDK。

## 4. 设计原则

### 4.1 Benchmark 与 SUT 解耦

- `BenchmarkAdapter` 负责题目、输入构造、输出归一化和评分规则；
- `SUTAdapter` 负责被测产品的会话、提交、轮询和结果收集；
- Orchestrator 只依赖两类 Adapter 的稳定接口；
- 禁止为某个“Benchmark × 产品”组合编写专用主流程。

### 4.2 Generation 与 Evaluation 分离

- Generation 调用 SUT 并生成不可变 Artifact；
- Evaluation 只读取 Artifact，不重新调用 SUT；
- Grader 版本变化时创建新 ScoreRecord；
- 报告变化时只重新聚合；
- 原始 Artifact 一旦完成写入，不得原地修改。

### 4.3 系统失败与答案错误分离

以下状态不得计为错误答案：

- 不支持任务能力；
- API 限流；
- 产品超时；
- 产品内部错误；
- 策略拒绝；
- Adapter 错误；
- Artifact 解析错误；
- Grader 错误；
- 人工执行不完整。

质量指标只在满足该指标最小可评分条件的样本上计算，并同时报告 coverage。

### 4.4 Evidence First

任何结果必须能够追溯到：

- 冻结后的题目和输入；
- 被测产品与模型版本；
- 原始请求和响应，或外部 job ID；
- 状态转换历史；
- 原始报告与附件；
- 评分器版本、配置和输出；
- 聚合规则。

### 4.5 幂等优先

- 每个任务提交前生成稳定幂等键；
- 服务恢复时必须先查询已有状态；
- 未确认外部任务不存在前，不得重新提交付费任务；
- 首个 SUT 必须支持 provider 端幂等键，或支持按幂等键查询已提交任务；
- 如果 provider 不具备上述能力，提交结果未知时必须转入人工处置，系统不得自动重提；
- transport retry、任务 retry 和重新生成必须记录为不同事件；
- 默认不允许自动重新生成内容。

## 5. 总体架构

```text
CLI / Future API
       │
       ▼
Run Service ─────────────── RunManifest Store
       │
       ▼
Orchestrator
 ├── Benchmark Registry ── BenchmarkAdapter
 ├── SUT Registry ──────── SUTAdapter
 ├── Scheduler / Runner
 ├── State Store ───────── SQLite
 ├── Event Store ───────── JSONL
 ├── Artifact Store ────── File System
 ├── Grader Router ─────── GraderAdapter
 └── Aggregator / Reporter
```

### 5.1 模块职责

#### Run Service

- 解析运行配置；
- 校验 Benchmark、SUT 和 Grader 版本；
- 生成不可变 `RunManifest`；
- 创建、恢复、取消和查询 Run。

#### Orchestrator

- 按状态机驱动任务；
- 执行能力协商；
- 调用 Adapter；
- 保存事件和 Artifact；
- 将失败转换为统一 FailureCategory；
- 保证阶段之间只通过类型化对象交互。

#### Scheduler / Runner

- 控制全局并发；
- 按 provider、endpoint 和 credential 分别限流；
- 调度轮询；
- 应用 deadline；
- 执行可重试操作；
- 防止单个 provider 阻塞整个 Run。

#### State Store

- 保存 Run、TaskRun、Submission、Attempt 和 GradingJob；
- 支持进程重启后的恢复；
- 使用数据库事务保护状态转换；
- 不存放大型响应正文。

#### Event Store

- 状态事件先写入 SQLite transactional outbox，再投影为 append-only JSONL；
- 每条事件包含序号、时间、实体 ID、事件类型和 payload；
- `(run_id, event_sequence)` 唯一，重复投影不得生成重复事件；
- 投影器中断后从最后确认序号继续，数据库 outbox 是事件完整性的事实来源；
- 用于审计和问题定位；
- Event 不代替 State Store。

#### Artifact Store

- 保存不可变原始请求、响应、报告、搜索结果和评分详情；
- 每个 Artifact 计算 SHA-256；
- 通过 URI 被数据库记录引用；
- MVP 使用本地文件系统，接口需允许未来切换对象存储。

#### Grader Router

- 根据 Benchmark rubric 解析所需 Grader；
- 硬评分优先，软评分后置；
- 每个 Grader 独立执行和缓存；
- 单个 Grader 失败不得破坏已有 Artifact 或其他评分结果。

## 6. 核心接口

### 6.1 BenchmarkAdapter

```python
class BenchmarkAdapter(Protocol):
    def spec(self) -> BenchmarkSpec: ...
    def load_tasks(self, split: str) -> list[TaskSpec]: ...
    def build_input(self, task: TaskSpec, ctx: RunContext) -> InputPackage: ...
    def normalize(
        self,
        raw: RawSUTResult,
        task: TaskSpec,
        ctx: RunContext,
    ) -> list[Artifact]: ...
    def required_graders(self) -> list[GraderSpec]: ...
    def aggregate(self, scores: list[ScoreRecord]) -> RunSummary: ...
```

要求：

- `load_tasks` 输出顺序稳定；
- `build_input` 必须是确定性的；
- `normalize` 不得发起 SUT 调用；
- Adapter 必须声明需要的能力；
- 不支持的能力在运行前返回 `UNSUPPORTED`；
- 官方评分语义不得被未经验证的自定义逻辑替换。

### 6.2 SUTAdapter

```python
class SUTAdapter(Protocol):
    def spec(self) -> SUTSpec: ...
    async def capabilities(self) -> CapabilitySet: ...
    async def start_session(
        self,
        task: TaskSpec,
        ctx: RunContext,
    ) -> SessionHandle: ...
    async def submit(
        self,
        session: SessionHandle,
        input: InputPackage,
        idempotency_key: str,
    ) -> Submission: ...
    async def poll(self, submission: Submission) -> JobStatus: ...
    async def collect(
        self,
        session: SessionHandle,
        submission: Submission,
    ) -> RawSUTResult: ...
    async def close(self, session: SessionHandle) -> None: ...
```

要求：

- API_SYNC Adapter 可在 `submit` 后直接返回完成状态；
- API_ASYNC Adapter 必须持久化外部 job ID；
- Adapter Spec 必须声明 `provider_idempotency` 与 `submission_lookup` 能力；
- Adapter 不负责评分；
- Adapter 不得吞掉 provider 的原始错误；
- 密钥不得进入 Artifact、Event 或日志；
- `close` 必须可重复调用；
- 所有网络操作必须设置 timeout。

### 6.3 ManualResearchImportAdapter

```python
class ManualResearchImportAdapter(Protocol):
    def spec(self) -> ManualImportSpec: ...
    def validate_package(
        self,
        package: ManualImportPackage,
        task: TaskSpec,
    ) -> ValidationResult: ...
    def collect(
        self,
        package: ManualImportPackage,
        task: TaskSpec,
    ) -> RawSUTResult: ...
```

人工导入不模拟 `submit/poll`。导入包必须包含操作者、执行时间、SOP 版本、原始报告和证据清单；缺失项作为结构化校验结果保存。

### 6.4 GraderAdapter

```python
class GraderAdapter(Protocol):
    def spec(self) -> GraderSpec: ...
    def supports(self, artifact: Artifact, task: TaskSpec) -> bool: ...
    async def grade(
        self,
        task: TaskSpec,
        artifacts: list[Artifact],
        ctx: GradeContext,
    ) -> list[ScoreRecord]: ...
```

要求：

- 输入仅来自冻结 Task 和 Artifact；
- Grader 输出必须包含版本、配置哈希和证据引用；
- LLM Judge 必须固定 provider、model、prompt、参数和地区；
- Judge 原始响应必须保存；
- 评分失败返回 `GRADER_ERROR`，不得伪造 0 分；
- 相同输入和配置优先命中评分缓存。

## 7. 数据模型

所有核心模型必须：

- 使用 Pydantic 定义；
- 包含显式 `schema_version`；
- 禁止未知字段或明确记录兼容策略；
- 时间统一使用 UTC ISO 8601；
- ID 使用 UUIDv7 或稳定命名 ID；
- 序列化输出必须可确定性排序和计算哈希。

### 7.1 RunManifest

至少包含：

- `run_id`；
- Benchmark ID、版本、split、commit SHA、数据哈希；
- SUT provider、product、model、endpoint family 和参数；
- Grader 列表、版本、prompt 哈希和配置；
- 并发、限流、poll、timeout 和 retry 策略；
- 预算上限；
- 随机种子；
- 创建时间、创建者和代码 commit SHA；
- 数据保留和脱敏策略。

Run 启动后不得原地修改 Manifest。配置变化必须创建新 Run。

### 7.2 TaskRun

至少包含：

- `run_id`、`execution_id`、`task_id`、`repeat_index`；
- 当前状态；
- attempt 计数；
- 幂等键；
- external job ID；
- deadline；
- 最近错误分类；
- 输入、输出和证据 Artifact URI；
- 创建、提交、完成和更新时间。

`execution_id` 唯一标识“一道任务的一次独立执行”。同一 Run 内
`(task_id, repeat_index)` 必须唯一。幂等键、Submission、Attempt、Artifact 和
ScoreRecord 均绑定 `execution_id`，避免重复运行覆盖数据。

### 7.3 Research Answer Artifact

统一使用 `trueeval.research_answer.v0.1`，至少包含：

- 原始最终回答；
- 原子 claims；
- citations；
- raw response、search results、trajectory URI；
- token、搜索次数、延迟和成本；
- SUT 身份信息；
- `completed`、`timeout`、`rate_limited`、`provider_error`、
  `policy_refusal`、`parse_error`、`cancelled` 等状态；
- 结构化错误信息。

### 7.4 ScoreRecord

至少包含：

- `run_id`、`execution_id`、`task_id`、`repeat_index`；
- `grading_job_id`；
- `grader_id` 和版本；
- metric 名称；
- 原始值和归一化值；
- coverage；
- rationale 或证据 URI；
- grader 配置哈希；
- 输入 Artifact 哈希；
- 状态与错误；
- 创建时间。

## 8. 状态机

### 8.1 TaskRun 状态

```text
CREATED
  → MATERIALIZED
  → READY
  → SUBMITTING
  → SUBMITTED ────────────────┐
  → COMPLETED_SYNC            │
                              ▼
  → RUNNING ↔ WAITING_EXTERNAL
       ├→ COMPLETED
       │    → COLLECTED
       │    → NORMALIZED
       │    → GRADING
       │    → SCORED
       ├→ FAILED_RETRYABLE
       │    → RETRYING
       │    → RUNNING
       ├→ FAILED_FINAL
       ├→ TIMED_OUT
       ├→ UNSUPPORTED
       └→ CANCELLED
```

`COMPLETED_SYNC` 与 `COMPLETED` 均进入 `COLLECTED`。人工导入从
`MATERIALIZED → WAITING_IMPORT → COLLECTED`，不经过提交和轮询状态。

### 8.2 状态转换要求

- 转换必须通过统一 State Transition Service；
- 每次转换在同一 SQLite 事务内更新状态并写入 outbox event；
- 非法转换必须抛出明确错误；
- 状态恢复必须从数据库状态开始，不得仅依赖日志；
- 已存在 external job ID 时不得重新调用 `submit`；
- 到达终态后只允许执行显式重评分，不允许回退状态；
- `SCORED` 不代表所有 Grader 成功，必须结合评分 coverage 判断。

阶段失败必须按下表处理：

| 阶段 | 可重试失败去向 | 不可重试失败去向 | 恢复动作 |
|---|---|---|---|
| materialize/build | `FAILED_RETRYABLE` | `FAILED_FINAL` / `UNSUPPORTED` | 重新执行纯函数并校验输入哈希 |
| start_session | `FAILED_RETRYABLE` | `FAILED_FINAL` | 创建新 attempt |
| submit | `WAITING_EXTERNAL` 或 `FAILED_RETRYABLE` | `FAILED_FINAL` | 优先按幂等键查询，未知状态不自动重提 |
| poll | `FAILED_RETRYABLE` | `TIMED_OUT` / `FAILED_FINAL` | 使用原 external job ID 恢复 |
| collect | `FAILED_RETRYABLE` | `FAILED_FINAL` | 使用原任务重新 collect |
| normalize | `FAILED_RETRYABLE` | `FAILED_FINAL` | 读取不可变 Raw Artifact 重跑 |
| grade | GradingJob 独立重试 | `GRADER_ERROR` | 不改变 TaskRun 的生成结果 |

TaskRun 描述执行生命周期；Research Answer Artifact 的 `status` 描述可交付结果。
执行尚未生成可保存结果时，不创建伪造的 Answer Artifact，只在 TaskRun 和 Error
Artifact 中记录失败。

## 9. 运行时工作流

### 9.1 创建 Run

1. 读取运行配置；
2. 解析 Adapter 与 Grader 版本；
3. 执行 Access & Compliance Gate；
4. 加载并冻结任务；
5. 生成题目快照和哈希；
6. 执行能力协商；
7. 生成不可变 RunManifest；
8. 创建 Run 和 TaskRun 数据；
9. 进入执行阶段。

其中每个任务按 `repeats` 展开为多个 `execution_id`，每次执行独立提交、存储和评分。

### 9.2 执行任务

1. `BenchmarkAdapter.build_input`；
2. 保存 Input Artifact；
3. `SUTAdapter.start_session`；
4. 生成幂等键并持久化；
5. `SUTAdapter.submit`；
6. 保存原始请求、响应和 external job ID；
7. 根据 channel 同步完成或异步 poll；
8. 达到完成状态后执行 `collect`；
9. 保存 Raw SUT Result；
10. 关闭 session；
11. 进入归一化。

### 9.3 归一化

1. 验证原始输出完整性；
2. 保留未经修改的最终回答；
3. 提取 claims、citations 和附件引用；
4. 记录不可观测字段为 `null` 或 `not_observable`；
5. 生成 Research Answer Artifact；
6. 计算哈希并落盘；
7. 更新 TaskRun 为 `NORMALIZED`。

禁止为了通过评分而补写引用、搜索结果或未返回的轨迹。
未经修改的原始响应保存在受控原件区；归一化和评分默认读取脱敏后的评测 Artifact。

### 9.4 评分

推荐顺序：

1. 格式和完整性校验；
2. 官方确定性 Grader；
3. 官方 LLM Judge；
4. 引用链接可访问性；
5. 引用相关性和事实支持；
6. TrueEval 诊断指标；
7. 聚合和异常检查。

每个 Grader 单独创建 GradingJob。失败的 Grader 可独立重试或重跑。每次重跑生成新的
`grading_job_id`，报告 Manifest 明确选择采用的 GradingJob，不以文件覆盖表示“最新”。

### 9.5 聚合与报告

报告至少包含：

- 总任务数和可评分任务数；
- completion、timeout、rate limit、provider error 等分布；
- 官方质量分；
- TrueEval 诊断分；
- 各指标 coverage；
- p50/p95 延迟；
- token、搜索次数和成本；
- 重复运行方差；
- 异常值和人工复核结果；
- Manifest 与证据索引。

不得只报告平均分而隐藏系统失败和 coverage。

## 10. 存储设计

### 10.1 目录结构

```text
runs/<run_id>/
├── manifest.json
├── events.jsonl
├── tasks.snapshot.jsonl
├── artifacts/
│   └── <execution_id>/
│       ├── input.json
│       ├── protected/
│       │   ├── raw_request.enc
│       │   └── raw_response.enc
│       └── evaluation/
│           ├── report.md
│           ├── search_results.json
│           └── research_answer.json
├── scores/
│   └── <grading_job_id>/
│       ├── manifest.json
│       └── scores.jsonl
├── summary.json
└── report.md
```

### 10.2 写入要求

- 文件先写临时路径，`fsync` 后原子 rename；
- Artifact 完成后计算并记录 SHA-256；
- JSON 使用 UTF-8；
- JSONL 每行必须是完整对象；
- 禁止在同一路径覆盖不同内容；
- 路径中不得直接使用未清洗的外部 ID；
- 数据库只保存 URI、哈希、状态和索引字段。
- 受控原件区加密保存完整证据，仅限授权审计访问；
- 评测区保存脱敏副本并记录其来源原件哈希；
- 原件与脱敏副本分别配置访问权限和保留周期。

### 10.3 SQLite 要求

- 开启 WAL；
- 启用 foreign key；
- 配置 busy timeout；
- 所有状态转换使用短事务；
- 状态表与 outbox event 在同一事务提交；
- 网络请求期间不得持有数据库事务；
- Schema 变化必须提供向前迁移脚本；
- 每次迁移前自动备份数据库。

## 11. 并发、限流与恢复

### 11.1 容量维度

至少分别维护：

- SUT 提交并发；
- SUT poll 并发；
- SUT collect 并发；
- 网页抓取并发；
- LLM Judge 并发。

不同 provider 和 credential 应使用独立 semaphore 与 rate limiter。

### 11.2 重试策略

可自动重试：

- 网络连接错误；
- 明确可恢复的 408、429 和 5xx；
- provider 明确标记为 retryable 的状态；
- 幂等 poll 和 collect。

默认不可自动重试：

- 认证失败；
- 参数错误；
- 能力不支持；
- 内容策略拒绝；
- 已成功提交但 job ID 丢失；
- 会产生新内容样本的重新生成。

重试采用带抖动的指数退避，并受总 deadline 约束。

### 11.3 进程恢复

启动时：

1. 扫描非终态 TaskRun；
2. 校验 Manifest 和 Artifact；
3. 对已有 external job ID 的任务恢复 poll；
4. 对 `SUBMITTING` 且结果未知的任务执行 provider 查询或人工确认；
5. 不确定是否提交成功时进入 `WAITING_EXTERNAL`；
6. 禁止无条件重新提交。

只有 provider 明确确认任务不存在，且重提仍使用 provider 端同一幂等键时，系统才可自动重提。

## 12. 配置规范

配置分为三类：

- 版本控制内配置：Benchmark、SUT、Grader 和默认策略；
- 单次 Run 配置：split、样本数、预算、并发、重复次数；
- Secret：API key、OAuth token、账号凭据。

Secret 只能从环境变量或 Secret Manager 注入，不得写入 YAML、Manifest、日志或 Artifact。

示例：

```yaml
schema_version: trueeval.run_config.v0.1
benchmark:
  id: browsecomp-zh
  split: pilot-25
sut:
  id: deepseek-research-api
  model: pinned-model-id
execution:
  repeats: 2
  submit_concurrency: 2
  poll_interval_seconds: 10
  task_timeout_seconds: 3600
  allow_regeneration: false
grading:
  graders:
    - browsecomp-official
    - cited-not-verified
budget:
  max_cost_usd: 100
```

运行时必须将最终解析后的配置写入 Manifest，而不是只保存用户输入片段。

## 13. CLI 设计

首版提供以下命令：

```text
trueeval benchmark validate <benchmark_id>
trueeval sut validate <sut_id>
trueeval run plan --config <path>
trueeval run start --config <path>
trueeval run resume <run_id>
trueeval run status <run_id>
trueeval run cancel <run_id>
trueeval import validate --run <run_id> --package <path>
trueeval import apply --run <run_id> --package <path>
trueeval grade run <run_id> --grader <grader_id>
trueeval report build <run_id>
trueeval artifact verify <run_id>
```

要求：

- `run plan` 不产生外部调用；
- `run start` 在提交付费任务前输出计划、样本数和预算；
- 破坏性或付费操作需要显式确认，可通过 CI 参数跳过交互；
- CLI 退出码必须可供自动化判断；
- 人类输出与结构化 JSON 输出分离。

## 14. 可观测性

### 14.1 日志

每条日志至少包含：

- `run_id`；
- `task_id`；
- `component`；
- `event`；
- `attempt`；
- `provider`；
- `duration_ms`；
- 错误分类。

日志不得包含 Secret、完整认证头和未经脱敏的个人信息。

### 14.2 指标

首版至少统计：

- Run 和 TaskRun 状态数量；
- submit、poll、collect 成功率；
- provider 错误和限流次数；
- 队列等待时间；
- 各阶段耗时；
- Grader 成功率；
- Artifact 校验失败数；
- token、搜索调用和成本。

### 14.3 审计

以下事件必须进入 Event Store：

- Run 创建、开始、取消和完成；
- Manifest 冻结；
- SUT 提交和 external job ID 绑定；
- 状态转换；
- 重试、超时和人工干预；
- Artifact 创建；
- Grader 执行；
- 报告发布。

## 15. 安全、隐私与合规

- Benchmark license 和数据使用限制必须写入 Benchmark Spec；
- 解密测试集不得上传到不受控服务；
- 运行前执行 Access & Compliance Gate，并生成包含 license、授权渠道、数据地区、
  数据保留和允许外发字段的版本化 GateRecord；
- Gate 判定为 `DENIED` 或信息不完整时禁止提交，结果与原因写入审计事件；
- 网页自动化必须确认账号、条款和授权；
- Artifact 需要可配置保留周期；
- 日志和报告不得泄露标准答案；
- 原始 prompt、响应和网页内容加密写入受控原件区；
- 个人信息在进入评测区、日志和报告前脱敏；
- 原件访问必须鉴权并记录审计，脱敏副本保存来源哈希；
- 人工导入必须记录操作者、时间、SOP 版本和证据清单；
- API 与网页结果可以比较输出质量，但必须保留不同 channel 标签。

预算控制采用“提交前预留、完成后结算”：Scheduler 在 SQLite 事务中按估算上限预留
单任务预算；预留后若超过 Run 硬上限则停止新提交；任务结束后回填实际费用并释放差额。
未知费用按预留额计算，预算事件进入审计记录。

## 16. 开发要求

### 16.1 代码要求

- 核心包采用 `src/trueeval/` 布局；
- 对外接口必须有类型标注；
- 核心 Schema、状态机和 Adapter 接口必须有文档字符串；
- 业务代码不得读取全局可变配置；
- 不使用裸 `except Exception` 吞掉错误；
- 网络、文件和数据库错误必须转换为统一错误类型；
- 时间、随机数、文件系统和 HTTP client 应可注入；
- 不在模块 import 时创建网络 client 或执行 I/O；
- Adapter 不得直接修改 Orchestrator 状态；
- Grader 不得修改输入 Artifact；
- upstream 代码通过封装调用，禁止散落复制。

### 16.2 依赖要求

- 所有运行依赖和开发依赖写入 `pyproject.toml`；
- 使用 lockfile 固定版本；
- 新增依赖必须说明必要性、license 和维护状态；
- 优先使用标准库或现有依赖；
- 禁止为简单状态机引入 Agent 框架；
- upstream Benchmark 依赖应隔离在 Adapter extra 中；
- CI 使用干净环境安装，禁止依赖开发机隐式包。

### 16.3 Schema 兼容要求

- Schema 字段变化必须更新 `schema_version`；
- 删除或改变语义属于 breaking change；
- Reader 至少支持当前版本和前一个版本；
- Migration 必须可重复执行；
- 历史 Artifact 不得因代码升级失去可读性；
- 未识别版本必须明确失败，不得静默猜测。

### 16.4 错误处理要求

统一错误至少包含：

- `category`；
- `code`；
- `message`；
- `retryable`；
- `provider_status`；
- `details_uri`；
- `cause_type`。

对用户报告安全信息，对内部 Artifact 保存足够诊断信息，但不得保存 Secret。

### 16.5 测试要求

#### 单元测试

覆盖：

- Schema 校验和序列化；
- 状态机合法与非法转换；
- 幂等键生成；
- 重试判定；
- Benchmark 输入构造；
- 输出归一化；
- Grader 缓存键；
- Artifact 哈希和路径安全。

#### 契约测试

每个 Adapter 必须通过统一 Contract Test：

- Spec 完整；
- capability 可解析；
- provider 端幂等或 submission lookup 能力已验证；
- poll 状态映射完整；
- collect 输出可归一化；
- provider 错误可分类；
- Secret 不进入日志；
- close 可重复调用。

#### 集成测试

使用 fake provider 验证：

- 同步成功；
- 异步成功；
- 429 后恢复；
- poll 超时；
- 进程重启恢复；
- submit 响应丢失；
- outbox 投影中断和事件重放；
- repeats 大于 1 时无路径或主键冲突；
- collect 失败后恢复；
- 单个 Grader 失败；
- 重评分不调用 SUT。

#### Golden Test

- 固定输入 Artifact；
- 固定 Grader 版本；
- 保存期望 ScoreRecord；
- 变更官方 prompt 或聚合逻辑时必须显式更新 golden；
- 更新时在 PR 中说明分数变化原因。

#### 端到端烟测

首轮使用 25 题分层样本，每题至少运行两次。必须验证：

- 无任务静默丢失；
- 所有原始请求和响应可追踪；
- 系统失败与错误答案分开；
- 官方评分可复跑；
- 搜索结果尽可能保存；
- 不可观测引用不被伪造；
- 成本、延迟和调用量尽可能记录。

### 16.6 质量门槛

合并前必须通过：

- formatter；
- linter；
- type checker；
- 单元测试；
- Adapter contract tests；
- Schema compatibility tests；
- Secret scanning；
- Artifact fixture 验证。

涉及状态机、幂等、重试、Manifest 或 Score 语义的变更必须由至少一名非作者评审。

## 17. 开发流程

### 17.1 需求进入

每项需求先明确：

1. 解决的是 Benchmark、SUT、Grader、Runner 还是 Report 问题；
2. 是否改变数据或评分语义；
3. 是否增加外部调用和费用；
4. 是否影响历史 Run 可读性；
5. 是否涉及 license、隐私或账号条款；
6. 是否需要 Schema 版本升级。

输出简短 Issue 或设计说明，包含范围、非目标和验收条件。

### 17.2 设计

以下变更必须先写设计：

- 新状态或状态转换；
- 新 Artifact 类型；
- 新 SUT channel；
- Grader 语义变化；
- 存储格式变化；
- 自动重试或重新生成策略变化；
- 新外部依赖；
- Temporal 等基础设施迁移。

设计必须说明失败模式、幂等、恢复、审计和兼容策略。

### 17.3 实现顺序

功能开发按以下顺序进行：

1. 定义或更新 Schema；
2. 编写状态机和接口契约；
3. 编写 fake 实现与失败场景测试；
4. 实现纯逻辑；
5. 实现文件和数据库持久化；
6. 实现外部 Adapter；
7. 增加 CLI；
8. 补充日志、指标和文档；
9. 执行离线与小样本验证。

禁止先接真实付费 API，再补状态持久化和测试。

### 17.4 Pull Request 要求

PR 描述至少包含：

- 变更目标和边界；
- 数据流或状态变化；
- 新增失败模式；
- 测试证据；
- 对历史 Run 的兼容性；
- 成本与安全影响；
- 必要的迁移或回滚步骤。

如果评分结果发生变化，必须提供同一 Artifact 在变更前后的分数对比及原因。

### 17.5 发布

发布步骤：

1. 在干净环境执行完整测试；
2. 运行 Schema migration dry-run；
3. 使用 fake provider 完成端到端测试；
4. 使用 3–5 个真实样本执行 canary；
5. 校验 Artifact、事件和报告；
6. 记录代码版本和配置版本；
7. 扩展到 25 题烟测；
8. 达到退出标准后扩大运行。

### 17.6 回滚

- 代码回滚不得删除已生成 Artifact；
- 新版本必须能读取旧版 Run；
- 数据迁移应优先采用可逆或前向修复方式；
- Grader 回滚通过指定旧版本重新评分完成；
- SUT 执行不可回滚，只能保留原始结果并创建新 Run。

## 18. 分阶段实施计划

### R0：离线评分闭环

交付：

- `pyproject.toml` 和依赖锁；
- 核心 Pydantic Schema；
- Artifact Store；
- GraderAdapter 与 Grader Router；
- 已有 cited-not-verified 流水线接入；
- 离线评分和报告 CLI；
- Golden tests。

退出标准：

- 给定冻结 Artifact，不调用 SUT 即可完成评分；
- 替换 Grader 版本后可重建报告；
- 每个分数可追溯到 Artifact 和 Grader 版本。

### R1：首个 Research Agent API

交付：

- SQLite State Store；
- 状态机与 Event Store；
- asyncio Runner；
- 一个同步或异步 SUTAdapter；
- submit、poll、collect、timeout、限流和恢复；
- Run CLI。

退出标准：

- 连续三轮小样本无静默丢任务；
- 进程重启后能够恢复；
- 每项结果可追溯到 request/response 或 external job ID；
- provider 端幂等或 submission lookup 已通过契约测试；
- 未知提交进入人工处置，系统不会自动重复付费提交。

### R2：人工导入

交付：

- ManualResearchImportAdapter；
- SOP 和证据清单版本化；
- Artifact 完整性校验；
- 人工 channel 标签和审计记录。

退出标准：

- API 与人工导入结果进入同一归一化和评分路径；
- 报告明确区分 channel；
- 缺失证据的任务被标记而非伪造补全。

### R3：授权网页自动化

不属于当前实现范围。进入 R3 前必须重新设计会话隔离、浏览器恢复、下载校验和合规控制。

## 19. MVP 验收标准

框架达到 MVP 可用状态必须同时满足：

1. 能通过配置创建一个冻结 Run；
2. 能对 25 题执行至少一个 Research SUT；
3. 能在进程重启后恢复非终态任务；
4. 无任务静默丢失；未知提交不自动重提，具备 provider 幂等能力时恢复不产生重复任务；
5. 原始请求、响应、报告和 external job ID 可追溯；
6. 输出统一归一化为 `trueeval.research_answer.v0.1`；
7. 至少支持一个官方 Grader 和 cited-not-verified；
8. 可不调用 SUT 重新评分和重建报告；
9. 系统失败、错误答案和不可评分样本分开统计；
10. 报告包含 coverage、成功率、质量、延迟和成本；
11. Secret 不出现在日志、Manifest 和 Artifact；
12. 单元、契约、集成和端到端测试全部通过；
13. `repeats >= 2` 时每次执行、Artifact 和评分均使用独立身份；
14. 人工导入包可校验、导入并进入与 API 相同的评分路径；
15. State 与事件 outbox 保持原子一致，JSONL 可从 outbox 重建；
16. Access & Compliance Gate 和预算硬限制能在提交前阻断运行。

## 20. 推荐代码目录

```text
src/trueeval/
├── cli/
├── core/
│   ├── schemas/
│   ├── state_machine/
│   ├── orchestration/
│   ├── errors/
│   └── hashing/
├── storage/
│   ├── state/
│   ├── events/
│   └── artifacts/
├── benchmarks/
├── suts/
├── graders/
├── reporting/
└── cited_not_verified/

tests/
├── unit/
├── contracts/
├── integration/
├── golden/
└── e2e/
```

现有 `trueeval/cited_not_verified/` 在 R0 中迁移到 `src/trueeval/`，迁移时保持公共行为兼容。

## 21. 待冻结事项

实现 R1 前必须确定：

1. 第一个 Research Agent API 及固定版本；
2. 第一个正式 pilot split；
3. Judge provider、模型、预算、地区和 prompt 版本；
4. Artifact 保留周期；
5. SQLite 到未来数据库的抽象边界；
6. 单任务与单 Run 的预算硬限制；
7. 人工复核比例；
8. 个人信息脱敏策略；
9. 附件型任务是否进入 MVP；
10. 报告的内部和公开范围。

## 22. 最终结论

TrueEval Deep Research MVP 应采用确定性 Python 工作流框架：

```text
Pydantic Schema
  + asyncio Runner
  + SQLite State Store
  + append-only Event Store
  + immutable Artifact Store
  + Benchmark/SUT/Grader Adapters
```

该方案不依赖 LangGraph，优先保证可恢复、可审计、可重评分和可扩展。规模扩大后可将 Runner 迁移到 Temporal，但评测数据契约和领域逻辑保持不变。
