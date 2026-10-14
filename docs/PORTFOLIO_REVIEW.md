# Documentation Status / 文档状态

[Home](../README.md) · [中文首页](../README.zh-CN.md) · [Q&A](Q_AND_A.md)

## Current scope / 当前范围

This public repository is a clean source export of private baseline `98dea9a8ecc889687031da09b79977aecd007295`, which included the earlier documentation work and the runtime changes reviewed in private PR #1 and PR #2. The old Git history remains private.

本公开仓库是私有基线 `98dea9a8ecc889687031da09b79977aecd007295` 的干净源码导出，包含此前文档整理及私有 PR #1、PR #2 审查过的运行逻辑。旧 Git 历史仍保留在私有仓库。

The publication work updates package descriptions, public links, and confirmed authorship, and omits the experimental `joblib` weight. It is not a new dialogue-feature iteration, a model retraining, or an online deployment. The official license text and public account identity remain unchanged.

本次公开准备同步打包说明、公开链接和已确认的作者信息，并排除实验性 `joblib` 权重；不是新一轮对话功能开发、模型重训或在线部署。许可证正文和公开账号身份保持不变。

## Documents in this snapshot / 本快照包含的文档

| Document / 文档 | Purpose / 用途 |
| --- | --- |
| [README](../README.md) | English project overview, design, setup, results, and limitations. / 英文项目介绍、设计、运行方法、结果与限制。 |
| [Chinese homepage](../README.zh-CN.md) | A Chinese introduction covering the same implementation and evidence. / 独立中文首页，与英文首页保持相同事实范围。 |
| [Architecture](ARCHITECTURE.md) | Processing flow, module responsibilities, session state, and key design decisions. / 处理流程、模块职责、会话状态与关键设计。 |
| [Evaluation](../EVALUATION.md) | Evaluation protocols, metric definitions, versioned results, and evidence limits. / 评测协议、指标定义、版本化结果与证据边界。 |
| [Q&A](Q_AND_A.md) | Common questions about operation, implementation, metrics, and current limitations. / 运行、实现、指标与当前限制的常见问题。 |
| [Local demo](DEMO.md) | Synthetic-input examples and local operating steps. / 合成输入示例与本地操作步骤。 |
| [Contributions](CONTRIBUTIONS.md) | Confirmed authorship and publication scope, with the recorded AI assistance. / 已确认的作者与公开范围，以及 AI 辅助记录。 |

The existing [model card](../MODEL_CARD.md), [privacy and safety document](../PRIVACY_AND_SAFETY.md), [third-party notices](../THIRD_PARTY_NOTICES.md), [license](../LICENSE), [citation metadata](../CITATION.cff), and [public-release checklist](../PUBLIC_RELEASE_CHECKLIST.md) remain the authoritative documents for their respective topics.

既有模型卡、隐私与安全说明、第三方声明、许可证、引用元数据和公开发布检查表，继续作为各自主题的主要依据。

## Publication checks / 公开检查

For this public snapshot, check that:

本公开快照应确认：

1. the English and Chinese homepages describe the same implemented system and recorded results;
2. essential technical terms are explained clearly enough for readers who have not opened the source code;
3. test and evaluation results remain attached to the correct code version;
4. the maintainer's authorship confirmation is distinguished from third-party artifact rights;
5. local links resolve and the documentation-related CI checks pass.

1. 中英文首页对系统功能和实验结果的描述一致；
2. 必要术语得到清楚说明，读者不必先阅读源码也能理解项目；
3. 测试和评测结果仍与正确的代码版本对应；
4. 本人独作确认与第三方权重再分发权利分别说明；
5. 本地链接有效，文档相关 CI 通过。

The maintainer has authorized this separate, code-only public repository. The publication does not include new screenshots, videos, or a hosted demo. That scope decision is not a claim that a new browser or live-provider acceptance run has passed.

维护者已授权建立这个单独的、只公开代码的仓库。本次不新增截图、录像或托管演示；这一范围决定不代表新一轮浏览器或真实服务商验收已经通过。

## Existing evidence / 已有证据

Private PR #1 and PR #2 were merged before the export. The historical private code baseline `d8e7aa4` passed 319 automated tests. Public-package results and the associated versioned metrics are documented separately in [EVALUATION.md](../EVALUATION.md); the historical result is not reused as a new test run.

导出前，私有 PR #1、PR #2 已合并。历史私有代码基线 `d8e7aa4` 曾通过 319 项自动测试；公开包验证及版本化指标在 [EVALUATION.md](../EVALUATION.md) 中单独记录，不把历史结果复用成新运行。

Historical browser checks and the later PA-A2/R1 and dialogue-quality spot checks keep their original version attribution. This public snapshot does not present them as new runs.

此前浏览器检查以及后续 PA-A2/R1、对话质量定点复验继续保留原版本归属，本公开快照不会把它们改写成本次新运行。

## Work that remains separate / 仍需单独完成的工作

The following remain separate from educational code publication:

以下事项与教学代码公开分别处理：

- live-provider protocol and credential-handling acceptance / 真实服务商协议及凭据处理验收；
- permission and packaging review before any future corpus-derived weight distribution / 未来如要分发语料派生权重，另行确认许可与打包范围；
- independent human scenario adjudication and real-user or clinical validation / 独立人工场景裁决、真实用户或临床验证；
- region-appropriate safety-resource availability before any deployment / 部署前确认适用地区及安全资源实际可用性；
- fresh authorization for any change beyond this public code snapshot, including a hosted service / 超出本次公开代码快照的变更，包括托管服务，需重新授权。

See [PUBLIC_RELEASE_CHECKLIST.md](../PUBLIC_RELEASE_CHECKLIST.md) for the complete list.

完整清单见 [PUBLIC_RELEASE_CHECKLIST.md](../PUBLIC_RELEASE_CHECKLIST.md)。

## Optional future media / 将来可选的素材

No new media is required for this publication. If screenshots or recordings are requested later, record the actual commit SHA, use synthetic input following [Local demo](DEMO.md), and keep unreviewed source material private before selecting sanitized files.

本次公开不要求新增素材。将来如需截图或录像，应记录实际提交 SHA，按照[本地演示](DEMO.md)使用合成输入；未经检查的原始素材先私下保留，再选择去隐私后的文件。

Provider credentials are not part of the documentation or media handoff.

模型服务凭据不属于文档或素材交接内容。
