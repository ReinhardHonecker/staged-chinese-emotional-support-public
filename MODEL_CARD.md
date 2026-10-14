# Model Card: Experimental Strategy Selector / 模型卡：实验性策略选择器

[Home](README.md) · [中文首页](README.zh-CN.md) · [Evaluation](EVALUATION.md)

## Summary / 概要

This card preserves the provenance and aggregate results of a **historical private experiment**. The public source distribution does **not** include `strategy_selector.joblib`, raw corpus data, sampled text, or teacher-label files. The size and hash below identify the historical artifact, not a downloadable file in this repository.

本模型卡保留的是**历史私有实验**的来源与汇总结果。公开源码发行**不包含** `strategy_selector.joblib`、原始语料、抽样文本或教师标签文件。下列体积与哈希用于标识历史权重，不表示本仓库提供该文件下载。

| Item / 项目 | Value / 内容 |
| --- | --- |
| Historical artifact / 历史权重文件 | `artifacts/strategy_selector.joblib` — not distributed / 不随包分发 |
| Version / 版本 | `soulchat-tfidf-logreg-v1-5447431b77` |
| Size / 大小 | `5,659,011` bytes / 字节 |
| SHA-256 | `26f5099ad6bbaa822afbe6569d6d1647de30bcb8bc9afc0bc56a0870663b13d1` |
| Deployment status / 部署状态 | **not accepted / 未通过** (`accepted: false`) |
| Method / 方法 | Character TF-IDF (2–5 grams), structural one-hot features, and class-balanced logistic regression / 字符 TF-IDF（2～5 gram）、结构字段 One-Hot 与类别平衡逻辑回归 |

The artifact predicts one of the project’s conversational support strategies. It does not generate reply text and does not decide S2–S4 safety routing.

该权重用于预测项目中的对话支持策略，不生成回复，也不参与 S2～S4 安全路由判断。

## Training provenance / 训练来源

- **Source corpus / 来源语料：** SoulChatCorpus. Complete provenance is recorded in `artifacts/strategy_data_manifest.json` and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- **Source sample / 来源样本：** 12,000 rows selected with random seed 42 / 使用随机种子 42 抽取 12,000 条。
- **Accepted training rows / 纳入训练：** 11,752。
- **Split / 数据切分：** grouped by conversation into train, validation, and test sets; recorded cross-group leakage is 0 / 按对话分组为训练、验证和测试集，记录的跨组泄漏为 0。
- **Historical teacher annotation / 历史教师标注：** DeepSeek V4 Flash as the primary teacher, with a 922-row audit by DeepSeek V4 Pro / DeepSeek V4 Flash 作为主要教师模型，DeepSeek V4 Pro 复核 922 条。
- **Primary-strategy agreement / 主策略一致率：** approximately 0.504 / 约 0.504。

Raw corpus data and teacher-label files are not distributed in this repository.

本仓库不分发原始语料或教师标签文件。

## Historical evaluation / 历史评测

| Metric / 指标 | Result / 结果 | Acceptance threshold / 验收门槛 |
| --- | ---: | ---: |
| Accuracy / 准确率 | 0.5929 | Report only / 仅报告 |
| Macro-F1 | 0.4973 | ≥ 0.55 |
| Weighted-F1 | 0.6530 | Report only / 仅报告 |
| Top-2 Accuracy / Top-2 准确率 | 0.8490 | ≥ 0.75 |

Macro-F1 did not meet the project’s activation threshold. Several long-tail strategies also had very few or no usable examples. The public distribution defaults to deterministic rules and includes no loadable classifier. Explicitly selecting `learned` therefore falls back to rules; it does not reproduce the historical learned-model experiment.

Macro-F1 没有达到项目设定的启用门槛，若干长尾策略的可用样本也很少，甚至为零。公开发行默认使用确定性规则，且不包含可加载的分类器；即使显式选择 `learned`，也会回退到规则，不能据此复现历史学习模型实验。

## Intended use / 预期用途

- Non-commercial NLP coursework, inspection of the recorded experiment, and reproduction of the rule-based system. Reproducing learned-selector training requires separately authorized data and artifacts; this distribution does not provide them.
  非商业 NLP 课程作业、历史实验记录查阅，以及规则系统复现。复现学习型策略训练需要另行取得合适授权的数据与产物，本发行不提供这些材料。
- Local experiments using synthetic text or text that has been appropriately authorized.
  使用合成文本或已取得适当授权的文本进行本地实验。

## Prohibited and out-of-scope use / 禁止及超范围用途

- Clinical diagnosis, treatment, triage, suicide-risk prediction, emergency response, or an unsupervised public service.
  临床诊断、治疗、分诊、自杀风险预测、紧急响应或无人监督的公共服务。
- Commercial use or redistribution beyond the project license and upstream terms.
  商业使用，或超出本项目许可与上游条款的再分发。
- Loading a modified or unverified artifact.
  加载被修改或未经验证的权重文件。

## Integrity and security / 完整性与安全

With no artifact present, the loader returns through the existing rule fallback without calling `joblib.load`. If a user separately supplies an authorized artifact, the loader checks its recorded byte size and SHA-256 before deserialization. A mismatch or missing metadata also disables it. A checksum confirms file identity, not trustworthiness or redistribution rights; joblib and pickle artifacts should still be loaded only from trusted sources.

缺少权重时，加载器直接使用已有规则回退，不调用 `joblib.load`。如果用户另行提供已获授权的权重，加载器会在反序列化前校验记录的字节大小和 SHA-256；校验不一致或元数据缺失时同样禁用。校验和只能确认文件是否一致，不能证明文件可信或具有再分发权限，因此 joblib/pickle 权重仍应只从可信来源加载。

## Limitations / 局限

The labels are model-assisted and partly subjective, teacher agreement is modest, and the corpus distribution is strongly imbalanced. The synthetic scenarios are engineering fixtures rather than clinical gold standards. The reported metrics therefore describe this experiment only; they do not establish real-user benefit or safety.

标签由模型辅助生成，带有一定主观性；教师模型一致率有限，语料分布也明显不平衡。合成场景属于工程测试样例，不是临床金标准。因此，现有指标只描述这项实验，不能证明对真实用户有效或安全。
