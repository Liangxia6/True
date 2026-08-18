# TrueEval Research Benchmarks

本目录保存 Benchmark 的版本化配置、官方上游文件、适配器和评分规则。产品执行代码不得直接依赖某个上游文件格式，应通过后续的 `BenchmarkAdapter` 转换为统一 `TaskSpec`。

## 当前数据集

| Benchmark | Track | Split | 数量 | 本地状态 |
|---|---|---:|---:|---|
| BrowseComp-ZH | short fact | `test` | 289 | 密文已入库；本机已生成明文任务与 gold |
| xbench-DeepSearch | short fact | `2505` | 100 | MVP；本机已生成明文任务与 gold |
| xbench-DeepSearch | short fact | `2510` | 100 | 非第一轮 MVP；本机已生成明文任务与 gold |
| DeepResearchEval | long form | `v1` | 100 | 可直接使用 |
| DeepResearchEval | long form | `v2_2601` | 30 | 可直接使用；动态时效题 |

版本与提取统计见 `INGEST_SUMMARY.yaml`。每个子目录均包含：

```text
<benchmark>/
├── benchmark.yaml       # 数据集版本、split、执行契约
├── rubric.yaml          # 官方指标和 TrueEval 诊断指标
├── upstream.lock.yaml   # 上游 commit、文件哈希、许可
├── adapters/            # 官方评分器兼容层
├── upstream/            # 固定版本的官方文件
├── tasks.jsonl          # TrueEval 统一题目；部分数据集仅本地生成
└── gold.jsonl           # 评分数据；不得传给被测产品
```

## 本地生成受保护数据

BrowseComp-ZH 和 xbench 的明文题目、答案及解密中间文件不得提交到 Git：

```bash
python3 scripts/benchmarks/decrypt_encrypted_to_trueeval.py
```

生成文件已经由仓库 `.gitignore` 排除：

- `benchmarks/browsecomp-zh/tasks.jsonl`
- `benchmarks/browsecomp-zh/gold.jsonl`
- `benchmarks/browsecomp-zh/local/`
- `benchmarks/xbench-deepsearch/tasks.jsonl`
- `benchmarks/xbench-deepsearch/gold.jsonl`
- `benchmarks/xbench-deepsearch/local/`

执行阶段只能读取 `tasks.jsonl`；`gold.jsonl` 仅允许评分阶段读取，避免答案泄漏。

## 第一轮 Research MVP 建议

1. 先用 xbench `2505` 的少量样本验证 Batch Runner；
2. 再执行 DeepResearchEval 长报告任务，验证长时间运行和成品采集；
3. BrowseComp-ZH 用于补充中文多跳检索，但不作为正式公开中文榜单；
4. xbench `2510` 暂不进入第一轮 MVP。
