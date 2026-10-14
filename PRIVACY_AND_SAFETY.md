# Privacy and Safety Boundary / 隐私与安全边界

[Home](README.md) · [中文首页](README.zh-CN.md) · [Architecture](docs/ARCHITECTURE.md)

## Default behavior / 默认行为

- The application starts in offline mode and does not contact an external model.
  应用默认以离线模式启动，不会联系外部模型。
- Conversation state remains in the current Streamlit session.
  对话状态保留在当前 Streamlit 会话中。
- Raw user text and generated replies are not written to disk by default.
  默认不把用户原文或生成回复写入磁盘。
- Anonymous runtime metrics are disabled by default. If enabled, they contain neither API keys nor message text.
  匿名运行指标默认关闭；即使启用，也不包含 API Key 或消息原文。

## Optional online mode / 可选在线模式

The sidebar can connect either an OpenAI-compatible Chat Completions endpoint or an Anthropic Messages endpoint. Before online mode is enabled, the user must acknowledge that the selected provider may receive:

用户可以在侧栏配置 OpenAI 兼容的 Chat Completions 端点或 Anthropic Messages 端点。启用在线模式前，需要明确知晓所选服务商可能收到：

- the current input after the application’s ordinary length limit is applied / 经过常规长度限制处理的本轮输入；
- a limited amount of recent history after locally handled safety episodes are filtered / 过滤本地安全片段后的有限近期历史；
- structured state derived from the conversation, including tentative analysis, user-confirmed corrections, safety-routing fields, and the current turn plan / 由对话推导出的结构化状态，包括暂定分析、用户已确认的纠正、安全路由字段和本轮计划。

Structured state is not a second copy of the conversation, but it may contain sensitive inferences derived from the user’s text. It should therefore be treated as sensitive data.

结构化状态并不是另一份对话原文，但其中可能包含从用户文本推导出的敏感判断，因此仍应按敏感数据处理。

Consent is checked continuously rather than only when a configuration is first applied. Withdrawing consent immediately disables the stored provider gateway and clears any API-key draft. Re-selecting the consent box alone does not restore previous credentials.

同意并不是只在首次配置时检查一次，而是持续生效的条件。撤回同意会立即停用已保存的服务商连接，并清空 API Key 草稿；仅重新勾选同意不会恢复此前凭据。

### API-key handling / API Key 的处理方式

- It is entered through a password field / 通过密码输入框填写；
- it is excluded from object representations and serialization / 不进入对象表示或序列化结果；
- it is held only by the provider client in the current session / 仅由当前会话的服务商客户端持有；
- it is cleared when consent is withdrawn, **Clear API configuration / 清除 API 配置** is selected, or the session ends / 撤回同意、点击“清除 API 配置”或会话结束时即被释放；
- it is never written to `.env`, logs, metrics, exports, or Git / 不写入 `.env`、日志、指标、导出文件或 Git。

Provider name, API URL, and model name are not treated as secrets, but they also remain within the current session.

服务商名称、API URL 和模型名不按秘密处理，但同样只在当前会话中保留。

Custom endpoints may receive sensitive text and derived state. Anyone using online mode should trust the endpoint operator and review that provider’s privacy, retention, and data-use terms. This project should not be deployed as a shared public server for collecting personal mental-health narratives.

自定义端点可能接收敏感文本和派生状态。使用在线模式前，应确认端点运营方可信，并审阅相应服务商的隐私、留存和数据使用条款。本项目不应部署成收集个人心理健康叙述的共享公共服务器。

## Safety routing / 安全分流

- The pipeline runs a context-aware S0–S4 precheck on the complete cleaned input before ordinary length truncation.
  管线会在普通长度截断前，对清洗后的完整输入执行具备语境判断的 S0～S4 预检。
- A current turn recognized as S2–S4 stays on the controlled local path. That turn and its derived state are not sent to the configured provider.
  当前轮次被识别为 S2～S4 时，会留在本地固定流程中；该轮文本及其派生状态不会发送给已配置的服务商。
- Explicit first-person harm language is checked conservatively outside quoted spans so that surrounding news, research, or third-party attribution does not automatically hide the current speaker.
  系统会在引号之外保守检查本人当前伤害表达，避免新闻、研究或第三方转述语境自动掩盖当前说话者。
- Locally handled safety episodes are removed from later provider-bound history. If the limited history window still contains a fixed safety-response marker or retained Safety metadata, the whole limited window is withheld rather than sending a partial episode.
  本地处理的安全片段会从后续准备发送给服务商的历史中移除。如果有限历史窗口仍含固定安全回复标记或“安全”阶段元数据，系统会舍弃整个窗口，而不是发送残缺的安全片段。
- S4 language uses a fixed reality-support protocol selected according to the risk subject and harm target. Third-party context takes priority over other-harm context, followed by the general first-person self-harm path.
  S4 语境会根据风险主体和伤害对象选择固定的现实支持流程，依次优先处理第三方语境、他伤语境，再进入本人自伤通用流程。
- During Safety, an existing ordinary action card remains in the session but is hidden together with its editor and download control. It can reappear when ordinary dialogue resumes; a later Act result may replace it.
  进入安全阶段后，既有普通行动卡仍保留在会话中，但卡片、编辑控件和下载入口会一起隐藏。恢复普通对话后可以再次显示，之后的新行动结果也可以替换它。
- Safety resources are region-specific and require periodic verification.
  安全资源与地区相关，需要定期核验。

These rules define an engineering boundary, not a clinical assessment or a guarantee of safety. Their effectiveness depends on the expressions that the finite local rules can recognize.

这些规则描述的是工程处理边界，不构成临床评估或安全保证；实际效果取决于有限规则能否识别相应表达。

## Non-medical disclaimer / 非医疗声明

This is an NLP course prototype. It cannot replace qualified mental-health professionals, medical diagnosis, emergency services, or local crisis resources. Do not rely on it as the sole response to an urgent or high-risk situation.

这是一个 NLP 课程原型，不能替代合格的心理健康专业人员、医疗诊断、紧急服务或当地危机资源。面对紧急或高风险情况时，不应把本系统作为唯一应对方式。
