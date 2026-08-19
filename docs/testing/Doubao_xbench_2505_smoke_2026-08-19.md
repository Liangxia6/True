# 豆包 xbench-DeepSearch 五题 Smoke Test

## 测试结论

- 日期：2026-08-19
- Run ID：`ff4913f4-21c6-43bc-ab9a-4ef87d7cde89`
- Benchmark：xbench-DeepSearch，版本 `17c562192cc7e62215bfb98b65e9f8806fb95504`
- SUT：豆包 Web Research
- 案例数：5
- 输出采集成功：5/5
- 系统失败：0
- 最终运行状态：`READY_FOR_GRADING`
- 正式评分：未执行；当前 Judge Profile 是示例配置，不能据此生成正式分数。

## 候选答案核对

| Task | 豆包提取结果 | Gold | 初步核对 |
|---|---:|---:|---|
| `xbench-deepsearch.2505.000001` | 161.27 元/克 | 161.27 元 | 一致 |
| `xbench-deepsearch.2505.000002` | 384 GFLOP/s | 384 GFLOPs | 一致 |
| `xbench-deepsearch.2505.000003` | 4 | 4 | 一致 |
| `xbench-deepsearch.2505.000004` | 292 | 292 | 一致 |
| `xbench-deepsearch.2505.000005` | 12 | 12 | 一致 |

这里的“一致”只是人工可读的候选答案核对，不替代 xbench 官方 Grader 或 TrueEval LLM Judge 的正式评分。

## 引用采集

豆包把来源渲染为可点击的 `span`，而不是普通 `a[href]`。点击来源标签后会打开原始来源页。Adapter 已增加双通道采集：先读取普通外链，再点击来源标签捕获新页签 URL，并按 URL 去重。

| Task | URL 数 | 来源 |
|---|---:|---|
| `000001` | 2 | 上海黄金交易所 PDF（2 份） |
| `000002` | 0 | 产品答案中未显示可解析来源 |
| `000003` | 0 | 产品答案中未显示可解析来源 |
| `000004` | 1 | 哔哩哔哩 |
| `000005` | 2 | 央视网、光明思想理论网 |

## 恢复与幂等性

首轮运行中，旧版提交确认逻辑对页面回显要求过严，导致 4 个已成功提交的任务被标记为 `SUBMISSION_UNCONFIRMED`。恢复程序只扫描并验证已有会话，不重新发送提示词；确认问题与完整答案匹配后，将 4 个案例恢复到正常状态。随后五题全部完成规范化并进入待评分状态。

## Artifact

运行目录：`artifacts/runs/ff4913f4-21c6-43bc-ab9a-4ef87d7cde89/`

- `report.json` / `report.md`：运行级报告；
- `cases/<task>/attempts/0001/raw/`：页面 HTML、可见文本、截图与事件；
- `cases/<task>/attempts/0001/normalized/research-submission.citations-refreshed.json`：回填引用后的规范化提交。
