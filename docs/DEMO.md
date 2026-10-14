# Local Demo / 本地演示

[Home](../README.md) · [中文首页](../README.zh-CN.md) · [Architecture](ARCHITECTURE.md) · [Q&A](Q_AND_A.md)

This guide uses synthetic Chinese inputs to walk through the main offline features. Keep the provider configuration empty and do not enter real private or sensitive experiences.

本指南使用合成中文输入体验主要离线功能。请保持在线模型配置为空，也不要输入真实的私人或敏感经历。

## 1. Start the application / 启动应用

Follow the installation commands in the [README](../README.md), then start Streamlit on `127.0.0.1`.

按照 [README](../README.md) 中的命令安装依赖，并让 Streamlit 只监听 `127.0.0.1`。

Before sending a message, confirm that:

开始前请确认：

- the page shows **Offline** / 页面显示 **Offline**；
- the model and API-key fields are empty / 模型与 API Key 为空；
- data-transfer consent is unchecked / 未勾选数据传输同意；
- the rule-based strategy selector is active / 策略选择使用规则方案。

Use a new conversation for each independent example. Keep the same conversation only when the instructions explicitly describe a multi-turn sequence.

每个独立示例都从新会话开始；只有明确标注为连续多轮的步骤才保留上下文。

## 2. Respect the current preference / 尊重当前偏好

Choose **Talk first / 倾诉** and send:

```text
别给建议，我今天只想把这件事说出来。
```

The reply should stay with the user’s current request. It should not invent an earlier mistake by the assistant or turn the message into an action plan.

观察回复是否尊重“现在只想说出来”的要求，没有虚构此前给错建议的经历，也没有直接生成行动方案。

## 3. Separate events, worries, feelings, and requests / 区分事件、担忧、感受与请求

Start a new conversation, choose **Organize / 梳理**, and send:

```text
项目截止是周五，我担心做不完，脑子很乱，帮我区分事实和担心。
```

Inspect both the reply and the analysis panel:

同时查看回复与分析区域：

- “项目截止是周五” should remain event information reported by the user / “项目截止是周五”应保留为用户提供的事件信息；
- “我担心做不完” should remain a worry about a possible outcome / “我担心做不完”应保留为对可能结果的担忧；
- “脑子很乱” should remain a self-reported feeling / “脑子很乱”应保留为用户对当前感受的描述；
- “帮我区分事实和担心” should remain the request for this turn / “帮我区分事实和担心”应保留为本轮请求。

The whole sentence should not be repeated as a fact, an unconfirmed interpretation, and the main blockage at the same time.

不能把整句话同时套成事实、未证实内容和核心卡点。

## 4. Continue from an option actually shown / 承接系统实际展示的选项

Start a new conversation, choose **Plan action / 行动**, and send:

```text
我可以先核对报名条件。我可以先检查设备电量。我可以先整理可用时间。先比较方向，暂时不决定。
```

Read the options shown on the page and note their order. In the recorded regression example, the second option is “检查设备电量”, but the page output you actually see is the source of truth for the next step.

先查看页面实际显示的选项及顺序。已有回归中第二项是“检查设备电量”，但下一步应以当前页面真实显示的内容为准。

In the same conversation, send:

```text
我选第二个。
```

The reply and action card should both refer to the second option from the preceding list. If the list is missing, rejected, or ordered differently, record the real result rather than altering the page or injecting session state.

检查正文和行动卡是否都对应上一轮实际展示的第二项。若列表没有出现、被拒绝或顺序不同，应保留真实结果，不要修改页面或注入会话状态。

## 5. Edit and download an action card / 编辑并下载行动卡

After a valid selection produces a card:

1. change one field using a synthetic value;
2. save the edit;
3. confirm that the page displays the new value;
4. download the JSON file and compare it with the saved card.

有效选择产生行动卡后：

1. 用合成内容修改一个字段；
2. 保存修改；
3. 确认页面显示新值；
4. 下载 JSON，并核对字段是否与已保存的卡片一致。

Editing or downloading the card should not add another user/assistant turn. Changing the downloaded JSON afterward does not count as evidence of what the application originally generated.

编辑或下载不应额外增加一轮聊天。事后手工修改下载文件，也不能作为程序原始输出的证据。

## 6. Try several boundary cases / 补充边界案例

| Case / 情形 | Input and setup / 输入与操作 | What to check / 检查重点 |
| --- | --- | --- |
| Explicit correction / 明确纠正 | New Organize conversation: `不是难过，我是生气，帮我理清楚。` | Anger becomes the confirmed primary emotion; rejected sadness is not kept as an active secondary label. / 主情绪采用愤怒，次情绪不保留被否定的悲伤。 |
| Negated selection / 否定选择 | Show the three-option list again, then send `我没有选第二个。` | The system asks for clarification instead of creating a card for the second option. / 系统先澄清，不为第二项生成新卡。 |
| Unsupported duration / 不支持的时长 | Offer `我可以用1.5分钟核对报名条件。我可以先检查设备电量。我可以先整理可用时间。先比较方向，暂时不决定。`, then select the first option. | `1.5 分钟` is not silently changed to five minutes. / 不能把 `1.5 分钟` 擅自改成五分钟。 |
| Ordinary software message / 普通软件报错 | New Organize conversation: `上传时系统提示是文件格式错误，我有点焦虑。` | The error remains available to analysis instead of being treated only as an attempt to reveal an internal prompt. / 报错内容应正常进入分析，不能仅因“系统提示”四字就按内部提示泄露处理。 |

A rejected emotion may still appear when the reply quotes the user’s correction. That quotation does not mean the emotion remains active in the state.

回复在解释纠正时可能引用被否定的原词，这不等于该情绪仍保留在有效状态中。

## 7. Capture screenshots or video / 保存截图或录像

When collecting media, record the checked-out commit SHA, Python and Streamlit versions, Offline status, synthetic inputs, selected support modes, conversation reset points, and original filenames.

采集素材时，建议同时记录实际检出的提交 SHA、Python 与 Streamlit 版本、页面离线状态、合成输入、所选支持方式、清空会话的位置以及原始文件名。

Useful screenshots include the separated problem information, the displayed options, and the matching action card. Cropping is fine when it improves readability, but it should not hide relevant errors or alter the text.

建议优先保存三类画面：问题信息区分、系统展示的选项、与选项一致的行动卡。可以为提高可读性进行裁剪，但不能隐藏相关错误或修改文字。

Before sharing any image, check the browser chrome, account information, local paths, and downloaded files for personal data. Keep raw material private and add only reviewed, sanitized files to the repository.

分享素材前，请检查浏览器边框、账号信息、本地路径和下载文件是否包含个人信息。原始素材应私下保留，只把经过检查和去隐私处理的文件加入仓库。
