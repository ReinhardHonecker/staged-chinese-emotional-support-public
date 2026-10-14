# Public-release Hold Checklist / 暂缓公开发布检查表

This checklist records the scope of the 2026-10-14 code publication. The owner authorized a new public repository without the old private Git history or experimental weight, not a public emotional-support service. Completed publication decisions and unperformed deployment validation are listed separately; unchecked deployment items are not represented as passed.

本表记录 2026-10-14 的代码公开范围。本人授权的是不含旧私有 Git 历史及实验权重的新公开仓库，不是面向公众的情感支持服务。已完成的公开决定与尚未进行的部署验证分列；未做的部署项目不冒充通过。

## Authorized publication scope / 已授权的公开范围

- [x] Reconfirm permission to publish the original project as a separate code-only repository: the maintainer confirmed sole authorship and publication rights.
      重新确认是否获准把原始项目作为单独的纯代码仓库公开：本人已确认独作及公开权利。
- [x] Retain the existing account handle and AI-assistance disclosure; do not add a real name or private contact details.
      沿用现有账号名及 AI 辅助说明，不新增真实姓名或私人联系方式。
- [x] Do not claim permission to redistribute the SoulChatCorpus-derived weight; publish without that weight and keep third-party provenance.
      不声称已取得 SoulChatCorpus 派生权重的再分发许可；公开范围排除该权重并保留第三方来源说明。
- [x] Obtain fresh, explicit approval for this new public repository; the original repository and its history remain private.
      已为这个新公开仓库重新取得明确授权；原仓库及旧历史仍保持私有。

## Package verification / 发布包验证

- [x] Verify the standalone public Git tree and new history: 85 files, no experimental weight or original private history, and no committed local evidence or generated logs. Text/commit pattern screening found only a synthetic Guard test token; no private-identity or credential finding remained. This is a bounded scan, not a security guarantee.
      核验公开 Git tree 及新历史不含实验权重、原私有历史、私人凭据、私人路径、本地证据或生成日志。
- [x] Run the public package's automated suite and offline evaluation without provider credentials; record the actual results separately from historical private CI. Local publication run: 319 passed, offline evaluation and pip check passed; see EVALUATION.md.
      在无服务商凭据环境运行公开包全量测试与离线评测，实际结果与历史私有 CI 分别记录。
- [x] Confirm the new repository's CI passes without secrets and uploads the offline evaluation artifact: [public run 38528204561](https://github.com/ReinhardHonecker/staged-chinese-emotional-support-public/actions/runs/38528204561), 319 passed, on initial public commit `432da021930c2697656bfe32d8964dc4b7ce3a80`.
      确认新仓库 CI 无需秘密即可通过并上传离线评测产物，只链接实际的新运行。
- [x] Keep explicit UI-mode adherence separate from experimental blind stage routing; do not describe the class-imbalanced no-mode baseline as general effectiveness.
      区分显式 UI 模式遵循与实验性盲阶段分流，不把类别不均衡的无模式基线说成普遍有效。

The historical browser acceptance and subsequent PA-A2/R1 and dialogue-quality spot checks keep their original version attribution. No new browser run, screenshot collection, video, or hosted demo is claimed for this publication.

历史浏览器验收及后续 PA-A2/R1、对话质量定点检查保留原版本归属。本次不声称新增浏览器运行、截图采集、录像或托管演示。

The public CI artifact upload was checked through job logs and metadata (ID `11876896911`, 2420 bytes at verification). The ZIP was not downloaded or content-compared; the workflow's 14-day retention is not permanent evidence hosting. Later commit checks are available from the repository's Actions page.

公开 CI 产物通过任务日志及元数据核验（核验时 ID `11876896911`，2420 字节），未下载 ZIP 或比对其内容。工作流的 14 天保留期不是永久证据托管；后续提交检查以本仓库 Actions 页面为准。

## Not validated for deployment / 尚未完成的部署验证

- [ ] Verify real-provider SDK/protocol behavior and complete a live-provider acceptance run before claiming online interoperability.
      在声称在线互操作已获验收前，核验真实服务商 SDK/协议行为并完成实际服务商验收。
- [ ] Independently adjudicate all synthetic scenarios before treating labels as human gold; `codex_refined` is not evidence of expert review.
      在把标签当作人工金标准前，独立裁决全部合成场景；`codex_refined` 不等于专家审查证据。
- [ ] Establish appropriate real-user and clinical evidence before making efficacy or medical claims; such claims are outside this educational publication.
      在提出效果或医疗主张前建立相应真实用户及临床证据；本教学代码公开不包含这些主张。
- [ ] Check region-specific safety-resource availability before deployment; official references alone do not establish real-time service availability.
      部署前确认适用地区及安全资源可用性；官方资料本身不能保证服务实时可用。

Official-source documentation was reviewed for the existing mainland-China safety resources. This was a source check only, not a test call or a guarantee of round-the-clock connection. No resource numbers or configuration were changed for publication.

本轮复核了既有中国大陆安全资源的官方来源，仅属于资料核对，并非实际拨测或全天接通保证。未为公开变更资源号码或配置。

Any future weight distribution or hosted service needs a separate permission and deployment review. These exclusions are deliberate publication boundaries, not completed validation.

未来如要分发权重或运营托管服务，需另行核对许可与部署条件。这些是本次明确排除的范围，不是已经完成的验证。
