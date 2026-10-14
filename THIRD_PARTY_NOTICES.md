# Third-party Notices and Data Provenance / 第三方声明与数据来源

[Home](README.md) · [中文首页](README.zh-CN.md) · [Model card](MODEL_CARD.md)

## SoulChatCorpus

The historical private strategy-classification experiment used a filtered sample of **SoulChatCorpus**. This public source distribution includes only the experiment's code, provenance, and aggregate records: it does not include the raw corpus, sampled training rows, teacher-label caches, upstream model weights, or this project's derived `strategy_selector.joblib` artifact.

历史私有策略分类实验使用经过过滤的 **SoulChatCorpus** 样本训练。公开源码发行只保留实验代码、来源与汇总记录，不包含原始语料、抽样训练数据、教师标签缓存、上游模型权重，也不包含本项目派生的 `strategy_selector.joblib` 权重。

- **Dataset / 数据集：** <https://www.modelscope.cn/datasets/YIRONGCHEN/SoulChatCorpus>
- **Project repository / 项目源码：** <https://github.com/scutcyr/SoulChat>
- **Source revision / 来源修订：** `f67630511a443f33517a1c4af61c379314f5c5c4`
- **Recorded source SHA-256 / 记录的来源 SHA-256：** `c604f4a8a0bed0498f26f9405045b37c36b61e6f81b4f7e288aef87281a6cdb1`
- **Recorded source size / 记录的来源大小：** `907380685` bytes / 字节
- **Sample SHA-256 / 样本 SHA-256：** `56d2549e7cb98ff2da6c79aaf6875963b3859d7073fda3b50a6bef8c28710032`

The historical provenance notes distinguish the upstream source-code license from restrictions described for upstream model weights. They are not a determination that this project's corpus-derived artifact may be redistributed. The public distribution excludes that artifact rather than inferring permission from a non-commercial label or from the maintainer's ownership of the original project code. Any separate use or redistribution of upstream data or derived weights still requires review of the applicable upstream terms.

历史来源记录区分上游源码许可与上游模型权重的限制，但这不构成对本项目语料派生权重再分发权限的确认。公开发行直接排除该权重，不因为标注“非商业”或维护者拥有原创项目代码的权利，就推定已经获得上游材料许可。另行使用或再分发上游数据、派生权重，仍须审查相应上游条款。

The historical classifier is not an upstream SoulChat model weight; neither is distributed here. Retained hashes and aggregate metrics are provenance records, not a substitute for the missing artifact or permission to redistribute it.

历史分类器不是上游 SoulChat 模型权重，两者均不在此分发。保留的哈希与汇总指标只是来源记录，不能代替未提供的权重，也不构成其再分发授权。

### Academic citation / 学术引用

Chen, Yirong, Xiaofen Xing, Jingkai Lin, Huimin Zheng, Zhenyu Wang, Qi Liu, and Xiangmin Xu. “SoulChat: Improving LLMs’ Empathy, Listening, and Comfort Abilities through Fine-tuning with Multi-turn Empathy Conversations.” *Findings of EMNLP 2023*, pp. 1170–1183. <https://aclanthology.org/2023.findings-emnlp.83/>

The citation above is preserved in its published form.

以上引用保留论文正式发表时的原始格式。

## Historical teacher annotation / 历史教师标注

Archived experiment metadata records DeepSeek V4 Flash as the primary teacher and DeepSeek V4 Pro as the audit teacher. These names describe the historical course experiment only. They are not runtime defaults, endorsements, bundled services, or redistributed provider outputs. Teacher-label files are not included in the repository.

存档实验元数据记录 DeepSeek V4 Flash 为主要教师模型、DeepSeek V4 Pro 为复核教师模型。这些名称只用于描述历史课程实验，不代表运行时默认值、产品背书、内置服务或被重新分发的服务商输出。教师标签文件未包含在仓库中。

## Runtime SDKs / 运行时 SDK

The application can call OpenAI-compatible Chat Completions endpoints through the `openai` Python package and Anthropic Messages endpoints through the `anthropic` Python package. These packages are installed from their own distributions and remain subject to their respective licenses and terms. No SDK source code is vendored in this repository.

应用可以通过 `openai` Python 包调用 OpenAI 兼容的 Chat Completions 端点，也可以通过 `anthropic` Python 包调用 Anthropic Messages 端点。这些依赖从各自的软件包分发渠道安装，并继续受各自许可与条款约束；本仓库不内置 SDK 源码。

## Safety-resource references / 安全资源来源

The mainland-China safety-resource configuration records its verification date and source URLs in `resources/safety_resources_zh_CN.json`. Before deployment or public use, the listed contacts should be checked again for regional relevance and freshness.

中国大陆安全资源配置在 `resources/safety_resources_zh_CN.json` 中记录了核验日期和来源 URL。在部署或公开使用前，仍需重新确认这些联系方式是否适用于相应地区并保持最新。
