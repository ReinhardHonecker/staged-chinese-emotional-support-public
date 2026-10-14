# Q&A / 常见问题

[Home](../README.md) · [中文首页](../README.zh-CN.md) · [Architecture](ARCHITECTURE.md) · [Evaluation](../EVALUATION.md) · [Local demo](DEMO.md)

This page answers common questions about how the project works, what its results mean, and where its current boundaries lie. The public source candidate was exported from private snapshot `98dea9a8` (runtime lineage `d8e7aa4`) without the experimental joblib artifact or old Git history. Historical results are distinguished from checks on this candidate.

本页集中回答项目怎样运行、各模块为什么这样设计，以及现有测试结果应如何理解。公开源码候选从私有快照 `98dea9a8`（运行代码源自 `d8e7aa4`）导出，不包含实验 joblib 权重或旧 Git 历史。历史结果与本候选的检查结果分别记录。

## 1. What does the project do? / 这个项目主要做什么？

It is a Chinese emotional-support dialogue system developed as an NLP course project. Instead of treating every message as the same generation task, the system first organizes the user’s reported situation, emotions, support intent, readiness for advice, and safety-related context. It then chooses a task for the current turn before generating a reply and, when appropriate, an action card.

这是一个中文情感支持对话课程项目。系统不会把每条消息都当成同一种生成任务，而是先整理用户陈述的处境、情绪、支持需求、是否愿意讨论建议以及安全语境，再决定这一轮应该继续倾听、帮助梳理、回应感受，还是讨论方向与行动。

Further reading / 延伸阅读：[Architecture](ARCHITECTURE.md)

## 2. Why use dialogue stages? / 为什么要划分对话阶段？

A fluent reply can still arrive at the wrong moment. Advice may be premature when the user only wants to talk, while detailed problem solving may be too demanding when the user first wants to slow down. Dialogue stages make the purpose of the current turn explicit and give the planner concrete limits.

回复通顺，不代表回应时机正确。用户只想倾诉时，直接给方案可能太早；用户此刻只想先缓下来时，复杂分析也可能增加负担。阶段划分把本轮任务明确下来，并进一步约束是否允许建议、最多给几个方向、最多问几个主要问题。

Further reading / 延伸阅读：[`stage_controller.py`](../modules/stage_controller.py)、[`response_planner.py`](../modules/response_planner.py)

## 3. Can it run without an API key? / 不填 API Key 能运行吗？

Yes. The default path uses local rules for analysis and dialogue decisions, then produces a reply through controlled Chinese templates. The interface, interpretation corrections, option handling, and action cards can all be used without configuring an online provider.

可以。默认模式使用本地规则完成分析和对话决策，再通过中文模板组织回复。界面、理解纠正、选项承接和行动卡都可以在不配置在线服务商的情况下运行。

Here, “offline” means that the application does not call an external model. Installing dependencies still requires network access.

这里的“离线”只表示程序不调用外部模型；安装依赖仍然需要网络。

Further reading / 延伸阅读：[Local demo](DEMO.md)

## 4. How do the online model and the strategy classifier differ? / 在线模型和策略分类器有什么区别？

They solve different problems. An online model may assist with state analysis, response generation, and review on ordinary turns. The local classifier reads text and structured features and predicts a support-strategy label; it does not generate the reply itself.

两者解决的不是同一个问题。在线模型可以参与普通轮次的状态分析、回复生成和辅助检查；本地分类器只根据文本与结构化特征预测支持策略，不负责生成对话文字。

This is why online/offline execution and rule/learned strategy selection are separate settings. The historical learned classifier did not meet its activation threshold and is not bundled in the public distribution. Without a separately supplied artifact, both `auto` and explicit `learned` mode fall back to rules.

因此，是否联网与是否采用学习型策略是两个独立设置。历史分类器没有达到启用门槛，也未随公开发行提供；没有另行提供权重时，`auto` 与显式 `learned` 模式都会回退到规则。

Further reading / 延伸阅读：[Model card](../MODEL_CARD.md)

## 5. What is the difference between a stage and a strategy? / 阶段与策略有什么区别？

A stage answers, “What is the main task of this turn?” A strategy answers, “How should that task be carried out?” Organize, for example, is a stage; summarizing the problem structure or asking one focused question are strategies that can support it.

阶段回答“这一轮主要做什么”，策略回答“怎样完成这个任务”。例如，“梳理”是一个阶段；总结问题结构、确认理解或提出一个聚焦问题，则是完成这一阶段任务的具体方式。

The turn plan combines the stage, a primary strategy, an optional secondary strategy, advice permission, and response limits.

本轮计划会把阶段、主策略、可选辅助策略、建议许可和回复限制放在一起。

## 6. Are the items in `facts` verified facts? / `facts` 字段中的内容已经被核实了吗？

No. The field stores event information extracted from the user’s account. The application does not independently verify deadlines, conversations, or other events described by the user.

没有。这个字段保存的是从用户陈述中提取的事件信息，程序不会独立核实某个截止时间、某次谈话或其他现实事件。

For example, “the deadline is Friday” can be stored as reported event information, while “I am worried I will not finish” remains a worry about a possible outcome. If the message does not contain enough event information, `facts` may remain empty.

例如，“项目截止是周五”可以记为用户提供的事件信息；“我担心做不完”仍然是对可能结果的担忧。输入中没有足够事件信息时，`facts` 可以为空，不需要把整段话强行补进去。

Further reading / 延伸阅读：[`state_analyzer.py`](../modules/state_analyzer.py)

## 7. What happens when the user corrects an emotion? / 用户纠正情绪判断后会怎样？

For the explicit correction forms covered by the current tests, the user’s correction is applied after automatic inference. The rejected emotion and any duplicate of the confirmed primary emotion are removed from the secondary list. The next turn is analyzed again, so the correction affects the current result without permanently fixing later turns to the same state.

对于测试中已经覆盖的明确说法，例如“不是难过，我是生气”，程序会在自动推断结束后采用本轮纠正，并从次要情绪中移除被否定的情绪以及与主情绪重复的项目。下一轮仍会重新分析，因此一次纠正不会永久锁定后续状态。

Further reading / 延伸阅读：[`test_pa_a2_semantics.py`](../tests/test_pa_a2_semantics.py)

## 8. How does “I choose the second one” become a concrete action? / “我选第二个”怎样对应到具体行动？

The system records only options that were actually shown in the final previous reply and that the parser could preserve completely. A later selection must refer unambiguously to that active list.

系统只保存上一轮最终回复中实际显示、并且能够完整解析的选项。用户随后说“我选第二个”时，程序会检查它能否唯一对应仍然有效的列表。

A different processed turn, a new offer, a completed selection, or entry into Safety invalidates or replaces the old options. The program does not search arbitrary earlier history for a matching number.

经过其他对话轮次、出现新列表、选项已经使用或进入安全流程后，旧列表会失效或被替换。程序不会仅凭一个编号，从很久以前的聊天记录里恢复可执行选项。

Further reading / 延伸阅读：[`choices.py`](../modules/choices.py)、[`conversation_state.py`](../modules/conversation_state.py)

## 9. Why does the system sometimes ask for clarification after a numbered choice? / 为什么说了编号，系统有时仍会要求澄清？

A number does not always express a confirmed choice. “I have not chosen the second one” is a negation. A multi-sentence option may also contain an important qualifier such as “save as a draft; do not send,” and some duration expressions are easy to misread.

出现编号不一定代表已经确认选择。“我没有选第二个”是否定；“先写邮件，只保存草稿，不要发送”中的后半句会改变动作含义；部分时长表达也可能被错误解析。

When the parser cannot preserve the complete option or resolve the reference with confidence, it asks for clarification instead of dropping information or guessing. This adds an extra turn in some cases, but avoids creating an action on an uncertain basis.

当前解析器无法完整保留选项或确定指代时，会先澄清，而不是忽略限定条件或自行猜测。这样有时会多一轮确认，但可以避免在依据不足时直接生成行动。

Further reading / 延伸阅读：[`test_dialogue_quality_review.py`](../tests/test_dialogue_quality_review.py)

## 10. How are the reply and action card kept consistent? / 正文和行动卡怎样保持一致？

The reply text and optional action card are stored in the same `GeneratedResponse` object. The checking stage selects the complete object, and the pipeline saves the card from that selected result.

正文与可选行动卡共同存放在 `GeneratedResponse` 中。检查阶段选择的是完整结果，处理流程随后直接保存这个结果中的卡片。

If the text is repaired without choosing a fallback, the card remains attached to that candidate. If a fallback is selected, the text and card are replaced together. Deterministic checks also inspect all eight text fields in the card.

如果只修正正文而没有切换到备用结果，卡片仍属于原候选；如果真正选择备用结果，正文和卡片会一起更换。行动卡的八个文本字段也会接受确定性检查。

Further reading / 延伸阅读：[`response_guard.py`](../modules/response_guard.py)

## 11. Why are both 100% and 64.44% reported for stages? / 为什么阶段指标既有 100%，又有 64.44%？

They come from two different evaluation protocols:

- **Explicit-mode adherence: 180/180.** The expected stage is used to choose a matching UI mode, and the test checks whether the system follows that supplied preference.
- **No-mode stage routing: 116/180 (64.44%).** The mode hint is removed by setting `selected_mode=None`, and the rule-based selector makes its own decision on the same synthetic set.

两个数字来自不同的评测条件：

- **显式模式遵循：180/180。** 评测先根据期望阶段选择对应的界面模式，再检查系统是否遵循这个偏好。
- **无模式阶段判断：116/180（64.44%）。** 评测刻意不提供模式提示，让规则选择器在同一组合成场景上自行判断。

The first result is not blind classification. The second is also highly imbalanced: Organize is correct on 4/43 labeled turns, and Support receives no predictions. The real interface always provides a user-selectable mode and defaults to Talk first.

前者不是无提示分类成绩；后者也存在明显类别偏差，梳理为 4/43，支持为 0/15。实际界面始终提供用户可选模式，并默认选择倾诉。

Further reading / 延伸阅读：[Evaluation](../EVALUATION.md)

## 12. What do 319 passing tests establish? / 319 项测试通过能说明什么？

The historical 319-test result shows that the recorded private code snapshot satisfied the suite's assertions. The tests cover modules, the offline processing pipeline, Streamlit AppTest behavior, and mock-provider paths. It is not automatically a test result for the public candidate without weights; that candidate must be checked separately and its actual result recorded in [Evaluation](../EVALUATION.md).

历史 319 项结果说明记录中的私有代码快照满足了现有测试实际检查的条件，包括模块测试、离线处理流程、Streamlit AppTest 和 mock 接口路径。它不会自动成为无权重公开候选的测试结果；候选必须另行检查，并在[评测说明](../EVALUATION.md)记录真实结果。

The number does not establish complete semantic correctness, live-provider quality, clinical validity, or real-user benefit. The project previously had a case where the stage label was correct but the reply still failed to separate facts from worries; that defect required content-level assertions and browser review.

这个数字不能证明所有语义都正确，也不能代表真实在线模型质量、临床有效性或真实用户获益。项目此前就出现过“阶段选对了，但事实与担忧没有分开”的情况，后来必须增加内容断言和页面复验才能发现并修复。

## 13. Why is the learned strategy model disabled by default? / 为什么默认不启用学习型策略模型？

Its recorded Macro-F1 is 0.4973, below the project threshold of 0.55. Top-2 Accuracy is 0.8490, but that does not compensate for the failed Macro-F1 gate or weak performance on long-tail classes.

因为记录的 Macro-F1 为 0.4973，低于项目设定的 0.55 启用门槛。Top-2 Accuracy 虽然达到 0.8490，但不能替代 Macro-F1，也不能消除长尾类别表现不足的问题。

Only the historical experiment's provenance and aggregate metrics are retained in this public distribution; the joblib weight is not shipped. The unchanged missing-artifact path uses rules even when `learned` is selected. The historical classifier predicted strategy labels only; it was not a compressed version of an online model's full generation ability. A new evaluation's `learned_experiment` field must be read with its strategy-source distribution: rule fallback is not a loaded-model experiment.

公开发行只保留历史实验来源与汇总指标，不分发 joblib 权重。已有的缺权重路径会使用规则，即使选择 `learned` 也如此。历史分类器只预测策略标签，并不是把在线大模型的完整生成能力压缩到了逻辑回归中。新评测中的 `learned_experiment` 字段必须结合实际策略来源解释：规则回退不等于加载模型开展实验。

Further reading / 延伸阅读：[Model card](../MODEL_CARD.md)

## 14. What information may be sent in online mode? / 在线模式下哪些信息可能发送给服务商？

An ordinary online request may include the length-limited current input, filtered recent history, and structured state derived from the conversation. Data transfer requires explicit consent. Withdrawing consent clears the stored gateway and API-key draft.

普通在线请求可能包含经过长度限制的当前输入、过滤后的近期历史，以及由对话推导的结构化状态。数据传输需要明确同意；撤回同意后，已保存的连接和 API Key 草稿会被清除。

Turns locally recognized as S2–S4 remain on the controlled local path, and locally handled safety episodes are removed from later provider-bound history. This protection still depends on the finite local rules recognizing the relevant language.

本地识别为 S2～S4 的当前轮次会留在固定的本地流程中，相关安全片段也会从后续准备发送的历史中滤除。但这一边界仍取决于有限规则能否识别相应表达。

A locally generated option-selection reply does not necessarily mean that the entire turn made no provider call: an earlier ordinary state-analysis step may already have used the configured provider.

还需要注意：某轮的选项回复由本地生成，不代表整轮一定没有外部调用，因为前面的普通状态分析可能已经使用了在线服务。

Further reading / 延伸阅读：[Privacy and safety](../PRIVACY_AND_SAFETY.md)

## 15. What remains incomplete? / 目前还有哪些工作没有完成？

The final code version has not completed a live-provider acceptance run or a real-user outcome study. No-mode stage routing remains imbalanced, option parsing is deliberately conservative, and the learned strategy classifier has not passed its activation threshold.

最终代码版本尚未完成真实服务商验收和真实用户效果研究。无模式阶段判断仍有类别偏差，选项解析采取保守策略，学习型策略分类器也没有达到启用门槛。

The maintainer has confirmed that the original project was an individual, AI-assisted work and authorized publication of their own code under the existing account handle. This does not grant rights to upstream corpus-derived weights, which are excluded. The candidate starts without the private repository's Git history. Code publication requires package/privacy checks; independent human adjudication of synthetic labels and region-specific service verification remain prerequisites for stronger evaluation or deployment claims, not completed work. No new demonstration or live-provider run is claimed.

维护者已确认原项目为本人独作、使用 AI 辅助，并授权使用现有账号名公开本人代码。这不授予上游语料派生权重的许可，因此本候选排除该权重。候选不继承私有仓库的 Git 历史。代码公开需要发布包及隐私检查；合成标签的独立人工裁决和地区服务可用性核验，仍是提出更强评测或部署主张前的待办，不是已完成事项。不声称新增了演示或真实服务商验收。

Further reading / 延伸阅读：[Public-release checklist](../PUBLIC_RELEASE_CHECKLIST.md)
