# TrueEval Research MVP：Benchmark 数据格式 V0.1

> 目标：把不同 Research Benchmark 的题目、标准答案、评分规则和上游来源转换为统一格式，同时保留官方评测语义，供 DeepSeek 等 Research Agent/API 自动执行。

## 1. 基本原则

1. 题目与答案分离：运行器只能读取 `tasks.jsonl`，不能读取 `gold.jsonl`。
2. 官方指标与 TrueEval 补充指标分离：分别使用 `official.*` 和 `trueeval.*` 命名空间。
3. 有官方评分代码时，优先保存并调用官方代码，不把它擅自改写成 LLM Judge。
4. 所有数据必须记录上游仓库、commit、文件路径、split 和 license。
5. 动态事实题必须提供 `as_of` 或网页快照版本；缺少时间边界的动态题不进入可复现主榜。
6. 缺失、系统失败、拒答和答案错误是不同状态，不能统一记为 0 分。
7. MVP 的标准被测输出是“最终答案 + 引用 + 原始搜索结果”；若接口不返回轨迹，则轨迹类指标标记为 `not_observable`。

## 2. 推荐目录

```text
benchmarks/<benchmark_id>/
├── benchmark.yaml        # Benchmark 元信息和默认运行条件
├── tasks.jsonl           # 可暴露给被测 Agent 的题目
├── gold.jsonl            # 私有标准答案、事实点和评分引用
├── rubric.yaml           # 官方及 TrueEval 评分规则
├── upstream.lock.yaml    # 上游版本、文件哈希、提取记录
└── adapters/             # 官方评分代码包装器；没有时可以为空
```

`task_id` 是四个文件之间的稳定主键。必须保留原仓库的题号，不能用行号代替。

## 3. Benchmark 元信息：`benchmark.yaml`

```yaml
schema_version: trueeval.research_benchmark.v0.1
benchmark_id: browsecomp
name: BrowseComp
benchmark_version: upstream-commit-or-release
domain: research
task_family: factoid_research

upstream:
  repo_url: https://github.com/OWNER/REPO
  commit_sha: FULL_40_CHAR_COMMIT
  dataset_path: path/in/repo
  evaluator_path: path/to/official/evaluator
  license: LICENSE_ID_OR_TEXT
  homepage: https://example.com

splits:
  - name: validation
    public_questions: true
    public_gold: false
    task_count: 100

default_execution:
  mode: submission
  timeout_seconds: 900
  max_attempts: 1
  internet_required: true
  allowed_tools: [web_search, browser]
  output_contract: research_answer.v0.1

official_metrics:
  - official.answer_accuracy

trueeval_metrics:
  - trueeval.citation_correctness
  - trueeval.citation_completeness
  - trueeval.source_quality
  - trueeval.temporal_validity
```

### `task_family` 枚举

- `factoid_research`：单一、可验证的短答案。
- `multi_hop_research`：需要组合两个以上独立事实。
- `list_research`：要求找齐满足条件的实体列表。
- `comparative_research`：需要比较多个实体并给出结论。
- `report_research`：需要生成带证据的长报告。
- `temporal_research`：答案受指定日期影响。
- `insufficient_evidence`：正确行为可能是说明证据不足。

## 4. 问题格式：`tasks.jsonl`

每行一个 JSON 对象。运行时只能把 `input` 和允许公开的 `constraints` 提供给被测 Agent。

```json
{
  "schema_version": "trueeval.research_task.v0.1",
  "task_id": "browsecomp.validation.000001",
  "benchmark_id": "browsecomp",
  "upstream_task_id": "000001",
  "split": "validation",
  "task_family": "multi_hop_research",
  "input": {
    "prompt": "原始问题，逐字保留；不得为了适配模型而改写",
    "language": "en",
    "as_of": null,
    "attachments": []
  },
  "expected_output": {
    "answer_form": "short_text",
    "citation_required": true,
    "structured_fields": []
  },
  "constraints": {
    "internet_required": true,
    "timeout_seconds": 900,
    "max_search_calls": null,
    "allowed_tools": ["web_search", "browser"],
    "forbidden_domains": [],
    "required_domains": []
  },
  "provenance": {
    "source_file": "upstream/path/data.jsonl",
    "source_row": 1,
    "source_hash": "sha256:...",
    "extraction_version": "extractor.v0.1"
  },
  "tags": ["multi-hop"]
}
```

### 字段要求

| 字段 | 必填 | 说明 |
|---|---:|---|
| `task_id` | 是 | TrueEval 稳定 ID，禁止随导入顺序变化 |
| `upstream_task_id` | 是 | 原 Benchmark ID |
| `input.prompt` | 是 | 原始题目文本 |
| `input.language` | 是 | BCP-47 简化语言码，如 `en`、`zh-CN` |
| `input.as_of` | 动态题必填 | ISO 8601 时间或日期 |
| `expected_output.answer_form` | 是 | `short_text/list/structured_json/report` |
| `citation_required` | 是 | Benchmark 未要求引用时也要明确为 `false` |
| `provenance` | 是 | 追踪原始行与哈希 |

题目文件禁止出现：标准答案、答案别名、评分关键词、参考 URL、必须命中的事实点和 Judge prompt。

## 5. 私有标准答案：`gold.jsonl`

```json
{
  "schema_version": "trueeval.research_gold.v0.1",
  "task_id": "browsecomp.validation.000001",
  "answer_type": "short_text",
  "reference_answer": "官方标准答案原文",
  "acceptable_answers": ["允许的别名或规范化形式"],
  "unacceptable_answers": [],
  "claims": [
    {
      "claim_id": "c1",
      "statement": "完成该题必须成立的原子事实",
      "importance": "required",
      "accepted_values": ["标准值"],
      "evidence": [
        {
          "url": "https://authoritative.example/source",
          "title": "Source title",
          "publisher": "Publisher",
          "published_at": null,
          "accessed_at": "2026-08-18T00:00:00Z",
          "snapshot_uri": null,
          "evidence_hash": "sha256:..."
        }
      ]
    }
  ],
  "temporal_scope": {
    "valid_as_of": null,
    "valid_from": null,
    "valid_until": null
  },
  "official_grader_payload": {},
  "provenance": {
    "source_file": "upstream/path/gold.jsonl",
    "source_row": 1,
    "source_hash": "sha256:..."
  }
}
```

规则：

- 上游只有一个字符串答案时，保留在 `reference_answer`，不要自动生成大量别名。
- 上游有分解事实或参考文献时，转换为 `claims`。
- `claims` 必须是可独立判真的原子事实，不能把整篇参考答案放成一个 claim。
- 上游评分器需要特殊字段时，原样放入 `official_grader_payload`。
- 不允许用待测 Agent 生成的数据反向补充 gold。

## 6. 评测标准格式：`rubric.yaml`

```yaml
schema_version: trueeval.research_rubric.v0.1
rubric_id: browsecomp.default.v1
benchmark_id: browsecomp

gates:
  - metric_id: trueeval.execution_success
    condition: status == completed
    on_fail: exclude_as_system_failure

metrics:
  - metric_id: official.answer_accuracy
    namespace: official
    role: score
    method: upstream_executable
    adapter: adapters/official_grader.py
    inputs: [prediction.final_answer, gold.official_grader_payload]
    range: [0.0, 1.0]
    weight: 1.0
    missing_policy: error

  - metric_id: trueeval.citation_correctness
    namespace: trueeval
    role: diagnostic
    method: claim_citation_entailment
    inputs: [prediction.claims, prediction.citations, artifacts.search_results]
    range: [0.0, 1.0]
    weight: 0.0
    missing_policy: not_observable

  - metric_id: trueeval.citation_completeness
    namespace: trueeval
    role: diagnostic
    method: weighted_claim_coverage
    inputs: [prediction.claims, prediction.citations]
    range: [0.0, 1.0]
    weight: 0.0
    missing_policy: not_observable

  - metric_id: trueeval.source_quality
    namespace: trueeval
    role: diagnostic
    method: source_quality_rubric
    inputs: [prediction.citations]
    range: [0.0, 1.0]
    weight: 0.0
    missing_policy: not_observable

  - metric_id: trueeval.temporal_validity
    namespace: trueeval
    role: gate
    applies_when: task.input.as_of != null
    method: evidence_date_check
    inputs: [task.input.as_of, prediction.claims, prediction.citations]
    threshold: 1.0
    missing_policy: fail

aggregation:
  official_primary: official.answer_accuracy
  trueeval_composite: null
  leaderboard_metric: official.answer_accuracy
  system_failures: report_separately
  confidence_interval:
    method: bootstrap
    samples: 10000
    confidence: 0.95
```

### 每个 Metric 必须描述

- `metric_id`：稳定、带命名空间的指标名。
- `role`：`gate`、`score` 或 `diagnostic`。
- `method`：具体执行方法，不能只写“LLM 评估”。
- `inputs`：评分器可读取的字段，防止评分时意外读取隐藏信息。
- `range`：分数范围。
- `weight`：只对复合分有效；诊断项初期为 0。
- `missing_policy`：`error/fail/zero/not_observable/exclude` 之一。
- `adapter` 或 `judge_config`：确保评分可复跑。
- `aggregation`：样本级如何形成 Benchmark 结果。

## 7. 标准被测输出

无论 DeepSeek API 返回什么原始结构，都归一化为下面的记录；原始响应单独保存，不覆盖。

```json
{
  "schema_version": "trueeval.research_answer.v0.1",
  "run_id": "uuid",
  "task_id": "browsecomp.validation.000001",
  "status": "completed",
  "final_answer": "被测 Agent 的最终输出原文",
  "claims": [
    {
      "claim_id": "p1",
      "text": "从最终答案切分出的原子主张",
      "citation_ids": ["src1"]
    }
  ],
  "citations": [
    {
      "citation_id": "src1",
      "url": "https://example.com/page",
      "title": "Page title",
      "quoted_text": null,
      "retrieved_at": "2026-08-18T00:00:00Z"
    }
  ],
  "artifacts": {
    "raw_response_uri": "artifact://...",
    "search_results_uri": "artifact://...",
    "trajectory_uri": null
  },
  "usage": {
    "input_tokens": null,
    "output_tokens": null,
    "search_calls": null,
    "latency_ms": 0,
    "cost_usd": null
  },
  "sut": {
    "provider": "deepseek",
    "product": "api_with_web_search",
    "model": "deepseek-v4-pro",
    "endpoint_family": "anthropic_messages",
    "parameters": {}
  },
  "error": null
}
```

`status` 枚举：

- `completed`
- `timeout`
- `rate_limited`
- `provider_error`
- `policy_refusal`
- `parse_error`
- `cancelled`

这些状态必须与“答案错误”分开统计。

## 8. 从其他仓库抽取时必须带回的内容

### 必须项

- 原始题目和稳定 ID；
- split 名称；
- 标准答案或官方私有答案字段；
- 官方评分代码及其配置；
- 答案规范化逻辑；
- 评分 prompt（如果官方本来就使用 Judge）；
- 聚合方式、阈值、置信区间算法；
- 仓库 URL、完整 commit SHA、源文件路径和文件哈希；
- license、数据使用限制；
- 依赖版本、模型/Judge 版本；
- 数据集发布日期和动态题的时间边界。

### 不够用的抽取结果

以下任一种都不能直接接入正式评测：

- 只有题目，没有 gold 或官方评分器；
- 只有 README 中公布的总榜结果；
- 把官方程序评分改成未经验证的 LLM Judge；
- 不记录 commit，只记录 `main` 或 `latest`；
- 动态题没有 `as_of` 或快照；
- 不清楚 license；
- 把测试集标准答案放进 Agent 可见的题目文件。

## 9. DeepSeek 首轮最小测试集

首轮不要直接跑完整 Benchmark。先从已接入数据中分层抽 25 题：

| 类型 | 数量 | 主要验证 |
|---|---:|---|
| 静态短答案 | 5 | API、解析、官方评分器 |
| 多跳事实 | 5 | 搜索与信息组合 |
| 动态事实 | 5 | `as_of`、新鲜度、来源日期 |
| 比较/列表 | 5 | 完整性、遗漏、结构化输出 |
| 证据不足/冲突 | 5 | 是否捏造、是否合理拒答 |

通过条件：

1. 25 题均有可追踪的原始请求和响应；
2. 系统失败与答案错误分开统计；
3. 官方指标可以复跑并得到相同结果；
4. Web Search 原始结果得到保存；
5. 引用不可观测时明确记录 `not_observable`，不伪造引用得分；
6. 同一任务至少重跑 2 次，用于观察结果方差；
7. 费用、延迟、token 和搜索次数能取到多少就记录多少，缺失保持 `null`。

## 10. V0.1 暂不做的事情

- 不把多个 Benchmark 强行换算成同一个百分制；
- 不把 TrueEval 诊断指标混入官方主分；
- 不使用专家分或用户盲测形成 Rank；
- 不对不可见的搜索轨迹做推测性打分；
- 不以网页端表现冒充 API 产品表现；
- 不将开发阶段 25 题结果发布为行业排行榜。
