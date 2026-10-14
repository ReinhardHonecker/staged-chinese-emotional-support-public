# Evaluation Protocol and Evidence / 评测协议与证据

[Home](README.md) · [中文首页](README.zh-CN.md) · [Architecture](docs/ARCHITECTURE.md) · [Q&A](docs/Q_AND_A.md)

This document separates four questions that are easy to confuse: whether the system follows an explicit support mode, whether it can choose a stage without that hint, whether the experimental classifier predicts a strategy, and whether the product behaves correctly in an end-to-end interaction. These are different measurements and should not be combined into one “accuracy” number.

本文把四类容易混淆的问题分开说明：系统是否遵循用户明确选择的支持方式、没有模式提示时能否自行判断阶段、实验性分类器能否预测策略，以及完整交互是否按预期运行。它们衡量的是不同能力，不能合并成一个笼统的“准确率”。

The public source candidate was exported from private snapshot `98dea9a8ecc889687031da09b79977aecd007295`, whose runtime code descends from `d8e7aa4` (private PR #2). The experimental joblib artifact and old Git history are not distributed. The version IDs and CI runs below are private historical records, not commits or downloadable evidence in this new repository. Earlier results remain attached to their original versions.

公开源码候选从私有快照 `98dea9a8ecc889687031da09b79977aecd007295` 导出，其运行代码源自 `d8e7aa4`（私有 PR #2）。实验 joblib 权重与旧 Git 历史不随包分发。下列版本和 CI 编号属于私有历史记录，不是新仓库中的提交或可下载证据；既有结果继续保留原版本归属。

## 1. Scenario set and execution scope / 场景集与执行范围

[`data/scenarios.json`](data/scenarios.json) contains 60 synthetic scenarios with three turns each, for a total of 180 turns. The status `codex_refined` means that Codex assisted with engineering refinement. It does not mean that the records were independently annotated by domain experts, clinically validated, or accepted as human-adjudicated ground truth.

[`data/scenarios.json`](data/scenarios.json) 包含 60 个合成场景，每个场景三轮，共 180 轮。`codex_refined` 表示这些样例经过 Codex 辅助的工程修订，不代表独立专家标注、临床验证或人工裁决金标准。评测器也接受 `approved` 状态，但字段名称本身不能证明每条记录都经过人工批准。

[`scripts/evaluate_scenarios.py`](scripts/evaluate_scenarios.py) directly calls local safety checking, offline analysis, stage selection, planning, template generation, and deterministic audit. It maintains its own conversation state and records the options displayed by the final response. It does not drive Streamlit and does not use the complete `process_message` path.

[`scripts/evaluate_scenarios.py`](scripts/evaluate_scenarios.py) 会直接调用本地安全检查、离线分析、阶段选择、规划、模板生成和确定性审计，并自行维护会话状态、记录最终展示的选项。它不驱动 Streamlit，也不是完整的 `process_message` 端到端路径。

The script runs three configurations over the same 180 turns: explicit rule, explicit learned, and no-mode rule. Repeating the same fixtures under different configurations does not create additional independent samples. When interpreting a learned-mode run, the strategy-source distribution must be checked because a failed or unavailable artifact can fall back to rules.

脚本会在同一 180 轮上运行显式规则、显式学习和无模式规则三种配置。不同配置重复使用同一批样例，不会产生新的独立样本。解释学习模式结果时，还要查看实际策略来源，因为权重不可用或未通过门槛时可能回退到规则。

The public candidate contains no learned artifact. Its `learned_experiment` arm therefore uses the existing rule fallback; the field name alone does not establish that a learned model ran. The complete report may differ from a historical report that included the artifact, even when the seven rule-based summary metrics match. This is a distribution boundary, not a new model comparison.

公开候选没有学习权重，因此 `learned_experiment` 分支会使用已有规则回退；不能仅凭字段名称就认定运行了学习模型。即使七项规则摘要相同，完整报告也可能与历史含权重报告不同。这是发行范围变化，不是新的模型对照实验。

## 2. Explicit UI-mode adherence / 显式 UI 模式遵循

In this protocol, the expected stage is deliberately mapped to a matching interface mode:

- Express → `我想先说说`
- Organize → `帮我理清楚`
- Support → `先帮我稳一下`
- Strategize or Act → `一起想办法`
- Safety → Talk first, with safety priority checked separately

该协议会根据期望阶段主动选择对应的界面入口：表达对应“倾诉”，梳理对应“帮我理清楚”，支持对应“先帮我稳一下”，协商与行动对应“一起想办法”；安全场景使用倾诉入口，并单独检查安全优先级。

`stage_accuracy_with_expected_ui_mode` therefore measures whether the implementation follows a supplied preference and its task constraints. Because the expected label helps choose the mode, the recorded **180/180 is not blind stage-classification accuracy**.

因此，`stage_accuracy_with_expected_ui_mode` 衡量的是系统能否遵循明确提供的支持方式及其任务约束。由于期望标签参与了模式选择，记录的 **180/180 不能当作无提示阶段分类成绩**。

## 3. Blind stage routing / 无模式提示的盲阶段分流

This protocol sets `selected_mode=None`, so the stage selector receives no mode derived from the expected label. It is an experimental offline diagnostic on the same synthetic set, not a separate test set. The real interface always offers a user-selectable support mode and defaults to Talk first.

该协议把 `selected_mode` 设为 `None`，不向阶段选择器提供由期望标签推导的模式提示。它是在同一组合成场景上的实验性离线诊断，并不是另一套独立测试集。真实界面始终提供可选支持方式，并默认选择倾诉。

The aggregate result must be read together with the class distribution. A single overall score hides the fact that the current selector strongly favors Express, rarely predicts Organize, and never predicts Support on this set.

总分必须结合逐类分布理解。单看 64.44% 会掩盖当前选择器明显偏向表达、很少预测梳理，并且在这组数据上从未预测支持的问题。

## 4. Historical evidence and public-candidate checks / 历史证据与公开候选检查

The weight-free public snapshot `0.2.0-public.1` was tested locally on 2026-10-14 with Python 3.12.13 and no provider credentials: **319 passed**, with no failures, errors, or skips. The offline evaluator and `pip check` also passed. Public CI is published separately in this repository's [workflow runs](https://github.com/ReinhardHonecker/staged-chinese-emotional-support-public/actions/workflows/ci.yml); historical private runs below are not substitutes for it.

无权重公开快照 `0.2.0-public.1` 于 2026-10-14 使用 Python 3.12.13，在无服务商凭据环境完成本地验证：**319 项通过**，无失败、错误或跳过。离线评测和 `pip check` 也通过。新公开 CI 以本仓库的[工作流运行](https://github.com/ReinhardHonecker/staged-chinese-emotional-support-public/actions/workflows/ci.yml)为准，下列私有历史运行不代替它。

The public run reproduced all seven rule-based summary values in the table below. Its complete JSON is **not equal** to the old weight-bearing report: `ab_comparison.learned_experiment.strategy_source_distribution` is now `{"rule": 180}`. Both configurations use rules, so their equality is not evidence of a learned model's performance.

公开包本次重现了下表全部七项规则摘要，但完整 JSON **不等于**旧含权重报告：`ab_comparison.learned_experiment.strategy_source_distribution` 现为 `{"rule": 180}`。两种配置实际都使用规则，因此相同结果不是学习模型效果证据。

One existing Streamlit test assumed model scores would exist after selecting learned mode. With no weight, the application correctly fell back but that assertion failed. The test now preserves the original nonempty-score assertion when a weight is installed and strictly verifies the absent-file reason, rule source/version, empty scores, offline execution, safe output, and the unavailable-weight UI caption otherwise. No production logic was changed, no test was skipped, and no thresholds were lowered.

一个既有 Streamlit 测试假定选择学习模式后一定有模型评分。移除权重后应用正确回退，但该断言失败。测试现保留“安装权重时评分非空”的原断言，并在缺权重时严格核验缺文件原因、规则来源与版本、空评分、离线执行、安全输出和界面的缺权重提示。没有修改生产逻辑，没有跳过测试或降低阈值。

| Evidence snapshot / 证据快照 | Version / 版本 | Recorded result / 记录结果 |
| --- | --- | --- |
| PA-A2 + R1, historical / 历史语义修复 | `625e7d2` (private / 私有) | 233 full tests; 28 focused tests are a subset / 全量 233，聚焦 28 为子集 |
| Dialogue-quality v2 head, historical / 历史第二轮对话质量修复 | `a4a0810` (private / 私有) | 319 full tests; 32 DQ-R1–R3 focused tests are a subset / 全量 319，DQ 专项 32 为子集 |
| Merged code baseline, historical / 历史合并代码基线 | `d8e7aa4` (private / 私有) | Same tracked tree as `a4a0810`; main CI passed 319 tests / 与 `a4a0810` 内容树相同，主分支 CI 通过 319 项 |
| Documentation snapshot, historical / 历史文档快照 | `98dea9a8` (private / 私有) | Main CI `34115571698`: 319 passed in 13.35s / 主分支 CI：319 项通过 |

Historical private main CI `34099227563` checked out `d8e7aa4` directly and recorded **319 passed in 13.01s**. The later private main CI `34115571698` checked out `98dea9a8` and recorded **319 passed in 13.35s**. Evaluation generation and artifact upload completed in both runs. Neither is a CI run for the new public repository.

历史私有主分支 CI `34099227563` 直接检出 `d8e7aa4`，记录 **319 passed in 13.01s**；随后私有主分支 CI `34115571698` 检出 `98dea9a8`，记录 **319 passed in 13.35s**。两次离线评测生成和产物上传均成功，但都不是新公开仓库的 CI 运行。

The uploaded artifact was verified through the workflow logs and artifact metadata. The ZIP was not downloaded for a complete remote-content comparison. Local acceptance records separately checked the evaluation JSON structure. An identical evaluation report also does not prove that every response string is identical, because the evaluator does not store the full text of every turn.

评测产物通过工作流日志和元数据核验，但没有下载 ZIP 做完整远程内容比对；本地验收记录另行检查了评测 JSON 结构。即使完整评测报告相同，也不能据此认定每轮回复文字完全一致，因为评测器并不保存所有轮次的完整正文。

<details>
<summary>Additional version provenance / 进一步版本信息</summary>

Before the private squash merge, historical push CI `33957797010` tested `a4a0810` directly and recorded 319 passed in 13.52s. Historical PR CI `33957824071` tested GitHub merge ref `43271da5d9fa8197ff5ce2adc62b88acc9baaf34` against `e4bef630` and recorded 319 passed in 12.95s. That merge ref was a test construction, not the actual merge commit.

合并前，push CI 直接测试 `a4a0810`；PR CI 测试 GitHub 临时构造的 merge ref。该测试 ref 只用于验证 head 与 base 的组合，不代表当时已经完成实际合并。

The historical merged code tree was `a7baf8a31962dc67824cb986c274beec66917b78`. Its `offline-evaluation-report` artifact ID was `10009814107`; the later `98dea9a8` run uploaded ID `10016117508`. These are historical upload records, not current download promises. The latter run's artifact listing was empty when checked on 2026-10-13; its workflow used a 14-day retention period. No remote ZIP-content comparison is claimed.

历史合并代码 tree 为 `a7baf8a31962dc67824cb986c274beec66917b78`，对应评测产物 ID 为 `10009814107`；后来的 `98dea9a8` 运行上传了 ID `10016117508`。这些只是历史上传记录，不保证现在可下载。2026-10-13 核验后一次运行时，产物列表已为空，其工作流保留期为 14 天；不声称已进行远程 ZIP 内容比对。

</details>

### Historical seven summary metrics / 历史七项摘要

| Key | Result / 结果 | Denominator and meaning / 分母与含义 |
| --- | ---: | --- |
| `scenario_count` | 60 | Three turns per scenario, 180 turns in total / 每场景三轮，共 180 轮 |
| `safety_route_accuracy` | 1.0 | 180/180 agreement with synthetic S0–S4 labels; not clinical sensitivity or specificity / 与合成程序标签一致，不是临床敏感度或特异度 |
| `stage_accuracy_with_expected_ui_mode` | 1.0 | 180/180 with UI modes chosen from expected stages / 使用期望阶段映射的界面入口 |
| `stage_accuracy_without_ui_mode` | 0.6444444444444445 | 116/180 without a mode hint / 无模式提示时 116/180 |
| `offline_behavior_clean_rate` | 1.0 | No listed deterministic-audit violation in 180 turns / 180 轮中未出现已列出的确定性审计违规 |
| `action_card_coverage` | 1.0 | 39/39 expected Act turns produced a nonempty card / 39 个期望行动轮均产生非空卡片 |
| `exact_repeated_response_rate` | 0.1111111111111111 | (180 − 160 unique strings)/180 in the explicit-rule protocol / 显式规则协议中的完全相同字符串重复率 |

An action card being present does not show that the advice is useful, that editing and downloading work, or that the card is semantically aligned with the reply. Those properties require separate tests. Exact repetition also measures identical strings, not semantic similarity.

产生行动卡不等于建议有用，也不等于编辑下载和正文一致性已经自动得到证明；这些需要独立检查。完全重复率只统计字面完全相同的字符串，不是语义相似度。

### Historical blind per-stage recall / 历史盲分流逐类召回

| Stage / 阶段 | Label count / 标签数 | Predicted count / 预测数 | Correct / 正确数 | Recall / 召回率 |
| --- | ---: | ---: | ---: | ---: |
| Express / 表达 | 45 | 100 | 42 | 0.9333 |
| Organize / 梳理 | 43 | 6 | 4 | 0.0930 |
| Support / 支持 | 15 | 0 | 0 | 0.0000 |
| Strategize / 协商 | 12 | 8 | 5 | 0.4167 |
| Act / 行动 | 39 | 40 | 39 | 1.0000 |
| Safety / 安全 | 26 | 26 | 26 | 1.0000 |

Recall uses the label count as its denominator. The current no-mode selector strongly favors Express; Organize recall is low, and Support receives no predictions. It should be treated as an experimental diagnostic rather than a replacement for the explicit support-mode selector.

召回率以该类别的标签数为分母。当前无模式选择器明显偏向表达，梳理召回率较低，支持在这组数据上为零预测。因此，它更适合作为实验性诊断，而不是替代界面的显式支持方式。

## 5. Historical PA-A2/R1 comparison / 历史 PA-A2/R1 对照

The fixed baseline `92031c4` had 104/180 correct no-mode stage predictions. The complete PA-A2 + R1 snapshot had 116/180. The per-turn comparison was:

| Outcome / 变化 | Turns / 轮数 |
| --- | ---: |
| Remained correct / 保持正确 | 80 |
| Corrected / 改对 | 36 |
| Newly incorrect / 新误分 | 24 |
| Still incorrect, prediction changed / 仍错但预测变化 | 34 |
| Same incorrect prediction / 保持原错 | 6 |

This is the effect of the complete PA-A2 + R1 change, not an improvement caused by R1 alone. The more conservative extraction of `facts` changed the input seen by the otherwise unchanged stage controller, so its insufficient-facts branch returned Express more often. Restoring the old whole-message fact filling would recover part of the old distribution at the cost of reintroducing the original semantic error.

这是完整 PA-A2＋R1 的变化，不能归因于 R1 单独提升。更保守的 `facts` 抽取改变了阶段控制器接收到的输入，使“事实不足”分支更常返回表达。恢复旧的整段事实回填，虽然可能追回部分旧分布，却会重新引入原来的语义错误。

R1 itself did not change the original scenario metrics. Its contribution—making explicit emotion correction take priority after recalculation—is supported by focused regression tests rather than the aggregate scenario score.

R1 单独运行没有改变原场景指标；它解决的是情绪纠正优先级问题，主要证据来自专项回归，而不是汇总分数。

## 6. What the separate regressions cover / 独立回归覆盖什么

### Safety and provider boundaries / 安全与服务商边界

Separate tests cover local S2–S4 handling, full-input safety checking before truncation, mixed-context overrides, and filtering of later provider history. The original 60 scenarios do not contain third-party S4 or other-harm S4 cases, so those branches are supported by dedicated synthetic pipeline regressions rather than the 60-scenario safety score.

独立测试覆盖本地 S2～S4、截断前完整扫描、混合语境处理以及后续服务商历史过滤。原 60 场景不包含第三方 S4 或他伤 S4，因此这些分支的证据来自专项 Pipeline 回归，而不是 60 场景安全分数。

### Response checks / 回复检查

The guard checks for empty output, length, question count, stage and advice constraints, diagnostic or coercive wording, unsupported certainty, and suspected leakage. It also scans all eight text fields in an action card. The guard selects a complete `GeneratedResponse`, keeping the reply and card from the same candidate.

Guard 会检查空回复、长度、问题数、阶段与建议约束、诊断或强迫性措辞、无依据的确定性表达和疑似泄露，并扫描行动卡的八个文本字段。它选择的是完整 `GeneratedResponse`，从而保证正文与卡片来自同一候选。

A safe candidate may be retained when a provider or schema error occurs, while an unsafe candidate triggers fallback or the fixed `guard_no_safe_response` path. These are deterministic checks with finite coverage, not a complete semantic evaluator.

服务商或结构异常时，原候选如果通过确定性检查，可以被保留并记录错误；候选不安全时，则进入备用结果或固定的 `guard_no_safe_response` 路径。这些是覆盖有限的确定性检查，并不是完整语义评估器。

### PA-A2/R1 semantic regressions / PA-A2/R1 语义回归

These tests cover event/worry/feeling/request separation, missing facts, attribution and qualifiers, explicit emotion correction after recalculation, and fresh analysis on the next turn. They were added because a correct stage label alone did not guarantee that the response completed the task.

这些测试覆盖事件、担忧、感受与请求的区分，事实不足、归属与限定，自动重算后的明确情绪纠正，以及下一轮重新分析。它们之所以必要，是因为阶段标签正确并不能保证回复真的完成语义任务。

### Dialogue-quality v2 regressions / 第二轮对话质量回归

These tests cover truthful current-preference wording, references to the final options displayed in the session, option expiry, negated choices, conservative rejection of incomplete multi-sentence options, unsupported timing, and ordinary software messages that should not be mistaken for internal-prompt disclosure requests.

这些测试覆盖当前偏好表述、不虚构此前行为、会话中最终展示的选项、选项失效、否定选择、多句选项的保守拒绝、不支持时长，以及不应被误判为内部提示泄露的普通软件报错。

The 32 DQ-R1–R3 tests are part of the full 319-test suite, not an additional sample total. The tested examples close the recorded O-01, O-02, and input-false-positive cases on those paths; they do not prove that every possible online generation error has been eliminated.

DQ-R1～R3 的 32 项测试属于全量 319 项的一部分，不能相加。它们关闭了对应路径中已记录的 O-01、O-02 和输入误报样例，但不表示所有在线生成问题都已被消除。

Scenario fields such as `must_include`, `must_avoid`, and `response_goal` provide a richer contract for human review. Not every field has been converted into an automated semantic assertion, so the repository does not claim that all 180 response contracts have been fully validated.

`must_include`、`must_avoid` 和 `response_goal` 为人工复核提供了更完整的要求，但它们尚未全部转化为自动语义断言，因此不能声称 180 轮回复合同已经全部验证通过。

## 7. Browser evidence and remaining limits / 浏览器证据与局限

The original A–E browser review ran on `92031c4`. A2 failed, while the other specified checks were completed and recorded. PA-A2/R1 later received targeted browser rechecks, and dialogue-quality-v2 received localhost spot checks including the final DQ-R1–R3 cases. The resumption of the submission process did not rerun the full browser suite because the source snapshot had not changed.

最初的 A～E 页面验收在 `92031c4` 上执行，A2 失败，其他指定检查有完整记录。随后，PA-A2/R1 进行了定点页面复验，第二轮对话质量也完成了包括 DQ-R1～R3 在内的 localhost 检查。恢复提交流程时源码快照没有变化，因此没有重复整套浏览器验收。

This documentation revision creates no new browser run. Remaining limitations include finite rules for negation, attribution, references, and time expressions; conservative rejection of ambiguous lists; generic clarification wording; no final-version live-provider acceptance; imbalanced no-mode routing; and no clinical or real-user outcome study. S0–S4 remain program states, not clinical grades.

本次文档修改没有新增浏览器运行。现有局限包括：否定、归属、指代和时间表达规则覆盖有限；歧义列表会被保守拒绝；澄清话术较为通用；最终代码版本尚未完成真实服务商验收；无模式阶段判断不均衡；也没有临床或真实用户效果研究。S0～S4 始终只是程序状态，不是临床等级。

## 8. Historical strategy-selector experiment / 历史策略分类实验

Strategy classification is separate from stage routing. The historical private character-TF-IDF and logistic-regression classifier achieved the following results. These numbers are not measurements of the public candidate's rule fallback:

策略分类与阶段分流不同。历史私有字符 TF-IDF 与逻辑回归实验取得以下结果；这些数字不是对公开候选规则回退路径的测量：

| Metric / 指标 | Result / 结果 |
| --- | ---: |
| Accuracy | 0.5929 |
| Macro-F1 | 0.4973 |
| Weighted-F1 | 0.6530 |
| Top-2 Accuracy | 0.8490 |

Macro-F1 was below the project's 0.55 activation threshold. Passing the Top-2 and artifact-size checks did not override that result. The historical artifact predicted a support strategy; it did not generate reply text or decide safety status. It is not included here, so `auto` and explicit `learned` mode fall back to rules in this distribution.

Macro-F1 低于项目设定的 0.55 启用门槛，Top-2 和权重体积检查通过不能替代这一结果。历史权重只预测支持策略，不生成回复，也不决定安全状态。本发行不包含该权重，因此 `auto` 与显式 `learned` 模式均会回退到规则。

The [model card](MODEL_CARD.md) and [metric artifact](artifacts/strategy_selector_metrics.json) document the dataset, grouped split, teacher agreement, long-tail limitations, and integrity checks. This documentation revision does not retrain or relabel the model.

数据来源、分组切分、教师一致率、长尾限制和完整性检查见[模型卡](MODEL_CARD.md)及[指标文件](artifacts/strategy_selector_metrics.json)。本次文档修改不重新训练或标注模型。

## 9. Reproduction / 复现

Use the Python 3.12 environment described in the [README](README.md):

```bash
python -m pytest -q
python scripts/evaluate_scenarios.py
python -m pip check
```

The existing [CI workflow](.github/workflows/ci.yml) runs tests and evaluation without provider credentials, then uploads the JSON as `offline-evaluation-report`. API paths are tested with mocks. Dependency installation and CI infrastructure still use network services, so this is not a network-isolation audit.

现有 [CI 工作流](.github/workflows/ci.yml) 会在没有服务商凭据的情况下运行测试和评测，并把 JSON 上传为 `offline-evaluation-report`；API 路径使用 mock。依赖安装和 CI 基础设施仍然使用网络，因此这不是网络隔离审计。

For a new run, record the actual checkout SHA and the results you observe rather than copying the numbers above.

重新运行时，应记录实际检出的提交 SHA 和真实输出，不要直接照抄本文数字。
