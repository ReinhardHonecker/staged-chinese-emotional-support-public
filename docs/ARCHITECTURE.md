# Architecture and Engineering Decisions / 架构与工程决策

[Home](../README.md) · [中文首页](../README.zh-CN.md) · [Evaluation](../EVALUATION.md) · [Q&A](Q_AND_A.md)

**Implementation lineage / 实现来源：** private runtime baseline `d8e7aa4`, exported through private snapshot `98dea9a8` without the experimental joblib artifact or old Git history / 私有运行代码基线 `d8e7aa4`，经私有快照 `98dea9a8` 导出，不包含实验 joblib 权重或旧 Git 历史。

This document explains how the current code turns one user message into a checked response. It focuses on control flow, state, and design decisions; evaluation results are documented separately.

本文说明当前代码怎样把一条用户输入处理成经过检查的回复，重点介绍控制流程、会话状态和关键设计。测试与评测结果另见 [EVALUATION.md](../EVALUATION.md)。

## 1. One controlled turn, not a fixed journey / 控制每一轮，而不是规定一条固定路线

Express, Organize, Support, Strategize, and Act are different tasks for the current turn. A conversation does not have to pass through them in order. The user can choose a support mode, while explicit intent and safety-related context may change the stage that is ultimately used.

表达、梳理、支持、协商和行动，描述的是当前这一轮要完成的不同任务。对话不必按固定顺序走完所有阶段。用户可以选择支持方式，明确的当前意图和安全语境也会影响最终采用的阶段。

The main execution path in [`process_message`](../modules/pipeline.py) is:

```text
Streamlit input + current session
  -> clean the complete input
  -> run the local safety precheck and mixed-context handling
  -> apply the ordinary input limit and filter provider-bound history
  -> analyze locally, or use provider-assisted analysis when allowed
  -> choose the dialogue stage
  -> plan the turn and resolve any active option reference
  -> generate locally, or use an online provider when allowed
  -> let the guard select a complete response/card result
  -> update session state and record the options actually displayed
  -> render the reply, correction controls, and permitted card controls
```

The safety precheck sees the complete cleaned input before ordinary truncation. If it selects S2–S4, the current turn bypasses ordinary provider-assisted analysis. Safety responses also account for who is at risk and whether the language concerns self-harm or harm to another person.

安全预检会先读取清洗后的完整输入，再进入普通长度限制。本地预检命中 S2～S4 时，当前轮次绕过普通在线分析。安全回复还会结合风险主体以及自伤、他伤等语境选择相应流程。

These protections depend on finite rules. They reduce several known failure modes but cannot guarantee that every real-world paraphrase will be recognized.

这些保护依赖有限规则，可以降低已经识别出的风险，但不能保证覆盖所有真实表达。

## 2. Module map / 模块分工

| Concern / 关注点 | Source / 源码 | Responsibility / 职责 |
| --- | --- | --- |
| UI and consent / 界面与同意 | [`app.py`](../app.py) | Session configuration, live consent, history entry, corrections, and card controls / 会话配置、持续同意、历史入口、理解纠正与行动卡控件 |
| Data contracts / 数据结构 | [`models.py`](../modules/models.py) | Pydantic objects for analysis, planning, generation, audit, and state / 分析、计划、生成、审计和状态对象 |
| Orchestration / 流程调度 | [`pipeline.py`](../modules/pipeline.py) | Processing order, safety precheck, filtered history, and final result / 执行顺序、安全预检、历史过滤与最终结果 |
| State analysis / 状态分析 | [`state_analyzer.py`](../modules/state_analyzer.py) | Offline rules, optional provider analysis, evidence spans, and explicit corrections / 离线规则、可选在线分析、原文证据与明确纠正 |
| Stage and strategy / 阶段与策略 | [`stage_controller.py`](../modules/stage_controller.py), [`response_planner.py`](../modules/response_planner.py), [`strategy_selector.py`](../modules/strategy_selector.py) | Stage priority, turn constraints, and rule-based or experimental strategy choice / 阶段优先级、本轮约束及规则或实验性策略选择 |
| Option references / 选项引用 | [`choices.py`](../modules/choices.py) | Bounded parsing of displayed options and the next selection / 对最终展示选项及下一轮选择进行有限解析 |
| Response realization / 回复实现 | [`response_generator.py`](../modules/response_generator.py), [`response_composer.py`](../modules/response_composer.py) | Controlled local templates, optional online generation, and structured actions / 受控本地模板、可选在线生成与结构化行动 |
| Guard and state update / 检查与状态更新 | [`response_guard.py`](../modules/response_guard.py), [`conversation_state.py`](../modules/conversation_state.py) | Selecting a complete response/card pair and updating the session / 选择完整的正文与卡片结果，并更新会话状态 |

The main NLP work lies in the connection between interpretation, dialogue state, policy, and language realization. Streamlit is the interaction layer. The project does not implement a new foundation model, a retrieval-augmented knowledge base, or a general-purpose autonomous agent.

项目的 NLP 重点在于把输入理解、对话状态、决策策略和语言实现连接起来；Streamlit 主要负责交互展示。本项目没有实现新的基础大模型、检索增强知识库或通用自主代理。

## 3. Two independent configuration axes / 两个相互独立的配置维度

| Axis / 维度 | Choices / 选项 | Meaning / 含义 |
| --- | --- | --- |
| Response execution / 回复实现 | Local templates or an explicitly configured provider / 本地模板或明确配置的在线服务商 | Offline results do not measure online-model quality / 离线结果不代表在线模型质量 |
| Strategy selection / 策略选择 | Rule, auto, or explicit experimental learned mode / 规则、自动或显式实验学习模式 | The classifier predicts a strategy; it does not generate text or decide safety status / 分类器只预测策略，不生成回复，也不决定安全状态 |

The historical private classifier did not pass its Macro-F1 threshold. Its joblib artifact is not included in this public distribution, so both `auto` and explicit `learned` selection use the existing rule fallback when no separately supplied artifact is present. Selecting `learned` does not by itself run the historical model or establish an A/B model comparison. See [MODEL_CARD.md](../MODEL_CARD.md) for historical provenance, metrics, and integrity checks.

历史私有分类器没有通过 Macro-F1 门槛，且其 joblib 权重不在本公开发行中提供。因此，没有另行提供权重时，`auto` 与显式 `learned` 都使用已有规则回退。选择 `learned` 本身不代表运行了历史模型，也不能据此建立模型 A/B 对照。历史来源、指标和完整性检查见 [MODEL_CARD.md](../MODEL_CARD.md)。

An ordinary online turn may use a provider for analysis, generation, and assisted review. When a previous option has been resolved—or when the system needs to clarify a choice—the final response is generated locally, but the earlier analysis step may already have contacted the configured provider. A locally generated final reply therefore does not automatically mean that the entire turn used zero provider calls.

普通在线轮次可能在分析、生成和辅助检查阶段调用服务商。对于已经解析出的选项或需要澄清的选择，最终回复由本地生成，但前面的状态分析仍可能已经调用在线服务。因此，“这一轮最终回复来自本地”并不等于整轮没有任何外部调用。

## 4. State and option lifetime / 会话状态与选项有效期

`TurnAnalysis` stores the system’s tentative interpretation. `TurnPlan` records the task actually selected for the turn, together with strategy, advice permission, and response limits. `GeneratedResponse` keeps the visible reply and optional `ActionPlan` together. `ConversationState` retains the current stage, previous analysis, corrections, saved card, and a bounded reference to recently displayed options.

`TurnAnalysis` 保存系统对当前输入的暂定理解；`TurnPlan` 记录本轮实际采用的任务、策略、建议许可和回复限制；`GeneratedResponse` 把可见正文与可选 `ActionPlan` 放在同一个结果中；`ConversationState` 则保存当前阶段、上一轮分析、用户纠正、行动卡和有限的近期选项引用。

Option memory is intentionally small. The session stores at most three `pending_options` and the `options_turn` that produced them. Options are recorded only after the final response has been selected, and they remain actionable only for the immediately following valid selection. Another processed turn, a successful selection, a new offer, or entry into Safety invalidates or replaces the old list. Ordinary UI reruns do not create a new dialogue turn.

选项记忆刻意保持很小：会话最多保存三个 `pending_options`，并记录它们出现的 `options_turn`。只有最终回复确定后才会登记选项，而且只承接紧接下一轮的有效选择。其他已处理轮次、成功选择、新列表或安全流程都会使旧列表失效或被替换；普通页面重跑不会自行增加对话轮次。

The parser is conservative. If a numbered option contains several sentences and an important qualifier cannot be preserved, the whole list is rejected. Unsupported duration expressions, such as decimal minutes, also lead to clarification rather than silently becoming five minutes. This sacrifices some coverage to avoid creating an action from incomplete information.

解析器采取保守策略。编号选项包含多句内容、且关键限定无法完整保留时，系统会拒绝整份列表；遇到小数分钟等不支持的时长表达，也会先澄清，而不是擅自改成五分钟。这样会少处理一些自然表达，但可以避免根据残缺信息生成行动。

## 5. Three design lessons from earlier defects / 从早期缺陷中得到的三个设计结论

### A. A correct stage label does not guarantee task completion / 阶段正确，不代表任务已经完成

An earlier Organize response repeated one mixed sentence as both a fact and an unconfirmed worry. The fix had to change both extraction and every relevant response template. A later correction-order defect showed the same principle: an explicit emotion correction was detected correctly, but automatic recalculation overwrote it afterward.

早期版本虽然进入了梳理阶段，却把同一整句同时写成事实和担忧。修复必须同时处理字段抽取与所有相关模板。之后的情绪纠正问题也说明了同一点：程序虽然识别到了用户纠正，但后续自动重算又把结果覆盖了。

**Design lesson / 设计结论：** stage labels and mechanical audits are necessary, but content-level assertions are still required. See [`test_pa_a2_semantics.py`](../tests/test_pa_a2_semantics.py) and the historical comparison in [Evaluation](../EVALUATION.md).

阶段标签和机械检查都很重要，但仍需要直接检查回复是否真正完成了语义任务。

### B. The guard must choose the reply and card together / 正文与行动卡必须作为一个结果被选中

A guard can repair the text without choosing a fallback. If downstream code then uses one broad Boolean flag to guess which card to save, the visible reply and stored action can come from different candidates. The guard now returns the selected `GeneratedResponse`, and the pipeline saves the card attached to that object.

检查模块可能只修正文，而不切换到备用结果。下游如果再用一个笼统的布尔值猜测该保存哪张卡片，就可能让页面正文和最终动作来自不同候选。现在由 Guard 直接返回选中的完整 `GeneratedResponse`，Pipeline 采用其中自带的卡片。

**Design lesson / 设计结论：** let one data contract own the invariant instead of reconstructing it later. See [`test_guard_generated_selection.py`](../tests/test_guard_generated_selection.py) and [`test_pipeline_guard_integration.py`](../tests/test_pipeline_guard_integration.py).

让同一个数据结构负责一致性，比在下游重新猜测来源更可靠。

### C. A numbered reference is not automatically permission to act / 出现编号，不等于已经确认行动

“I have not selected the second option” once matched a selection verb. A multi-sentence offer could lose the qualifier “draft only; do not send,” and a decimal duration could be read from its integer suffix. The current resolver checks polarity, option ownership, preserved qualifiers, and supported timing before creating a card.

“我没有选第二个”曾因包含选择动词而被误判为确认；多句选项曾丢掉“只存草稿，不要发送”，小数时长也曾只匹配整数尾部。现在，系统会在生成行动卡前检查肯否、选项归属、关键限定和受支持的时长表达。

**Design lesson / 设计结论：** clarification is preferable to silently executing an uncertain interpretation. See [`test_dialogue_quality_review.py`](../tests/test_dialogue_quality_review.py).

当指代不够明确时，多问一句比悄悄执行错误理解更合适。

## 6. Privacy and safety boundaries / 隐私与安全边界

Live consent controls whether the stored provider gateway is active. Withdrawing consent clears both the gateway and the API-key draft. Provider-bound history is filtered locally; if the limited history window contains retained Safety metadata or a fixed safety-response marker, the window is withheld rather than sending a partial safety episode.

持续同意决定已保存的服务商连接是否可用。撤回同意后，连接和 API Key 草稿都会被清除。发送给服务商的历史会先在本地过滤；如果有限历史窗口中仍含安全阶段元数据或固定安全回复标记，系统会舍弃整个窗口，而不是发送残缺的安全片段。

Ordinary online requests may still contain sensitive derived state. Deterministic guard checks cover the reply and all eight text fields in an action card, but they remain bounded checks rather than complete semantic protection. S0–S4 are program routing states, not clinical risk grades. Regional safety resources also require periodic review before public use.

普通在线请求仍可能包含敏感的派生状态。确定性 Guard 会检查正文和行动卡的八个文本字段，但这类规则不是完整的语义防护。S0～S4 是程序路由状态，不是临床风险等级；地区安全资源在公开使用前也需要定期核验。

See [PRIVACY_AND_SAFETY.md](../PRIVACY_AND_SAFETY.md) for the complete data boundary.

## 7. What the evidence covers / 现有证据覆盖什么

The full automated suite includes unit tests, real offline pipeline tests, Streamlit AppTest checks, and mock-based provider tests. The 60-scenario evaluator calls components directly and maintains its own state; it is not the complete Streamlit or `process_message` path. Those paths are supported by separate integration tests and recorded local browser checks.

全量自动测试包含单元测试、真实离线 Pipeline、Streamlit AppTest 和 mock 服务商路径。60 场景评测器会直接调用组件并自行维护状态，并不等同于完整 Streamlit 页面或 `process_message` 路径；后两类行为由独立集成测试和已有本地浏览器记录补充。

This documentation revision does not create a new browser run, live-provider experiment, clinical evaluation, or real-user study. For metric definitions and versioned evidence, see [EVALUATION.md](../EVALUATION.md).

本次文档修改没有新增浏览器运行、真实服务商实验、临床评测或真实用户研究。指标定义与版本证据见 [EVALUATION.md](../EVALUATION.md)。
