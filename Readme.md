## ✅ Floodgate 是什么
#### Floodgate 是一个桥接 [QQ 机器人开放平台](https://bot.q.qq.com/) 和 [OneBot v11](https://onebot.dev/) 协议的中间件框架<br>支持通过 Webhook 接收事件并将其转发至 OneBot 客户端，基本兼容OneBotv11，并提供了一些灵活的扩展接口。

### 💡 我们为何存在？

Floodgate 并不是为了挑战谁，也不为了证明什么。它的出现，仅仅是因为艾斯相信一件简单的事：

> **技术，应该服务人，而不是控制人。**

我们看到许多开发者因为生态封闭、规则混乱、态度傲慢，被迫「兼容」，被迫「迁就」，甚至被迫「臣服」。<br>
Floodgate 就是为这些开发者打造的出口 —— **你不需要去求谁，你只需要做你想做的**。

---

### ❌ 我们反对什么？

Floodgate 坚决反对任何**滥用项目影响力、试图主导技术标准并打压他人自由表达的行为。**

我们拒绝：

* 技术傲慢：「你不配用我写的代码」「我说没技术你就不许写」；
* 利用项目操控用户：「不顺我意就停更」「要不要继续维护，看你态度」；
* 打击异见：「这群人只会捡屎吃」「不跪着感谢就别用我的项目」；
* 社区暴力：「艾特全体」「带头网暴素人开发者」「公开嘲讽、造谣」。

这些行为不仅严重违背了开源精神，更破坏了一个正常开发者社区应有的尊重与协作氛围。

若您存在心理方面的问题，请及时寻求专业的心理支持，而不是在社区中四处纵火。

---

### ✅ Floodgate 提供什么？

我们不承诺最潮的技术栈，也不会逼迫你用最新的平台。

我们能体会到，一位成年人看到儿时的玩具时的念旧心。我们尽量兼容了**OneBot11的消息特性**，

Floodgate 项目始终秉持以下信条：

* 🚫 不用技术威胁社区，也不操控对话氛围；
* 🔄 鼓励 Pull Request，哪怕是新手的尝试也值得欢迎；
* 🌐 我们使用宽松的 [MIT License](https://opensource.org/licenses/MIT)，因为我们相信创意应当自由传播；
* 🤝 我们尊重每一位开发者，**聚散终有时，我们可能会停更，但我们不会以停更要挟用户**；
* ❤️ 我们致力于成为一个**工具型项目**，我们负责向下兼容，用户负责更快做出有趣、有爱的 bot，而不是困在「不断学步的轮回」中。

---

## 🚫 Floodgate 不是什么

请注意，**Floodgate 不是一个绝对标准的 OneBot 实现**。它并非旨在兼容所有 OneBot 客户端，或完整实现 OneBot v11 协议的全部特性。

Floodgate 是一个为 **DeluxeBOT** 特化设计的 `“类 OneBot v11”-QQ 协议转换中间件`，它的构建目标是服务于特定工作流，而不是通用适配。

* ❌ 它**不完全支持所有 OneBot 消息段或插件功能，[消息特性支持对比](#-项目特点)**
* ❌ 它**尽量支持未在 DeluxeBOT 场景中使用的ob11协议行为**
* ❌ 它**不会主动对协议做泛化适配，泛化适配可能带来潜在的安全风险，目前的Floodgate是相对安全的**

#### Floodgate 具有一些原本不属于 OneBot v11 协议的功能，如：消息去重、自动格式美化、频道图床、断联消息等，需开发者自行适配 。
某些你期待的功能如果“**艾斯不会用到**”，那就很可能“**不会做**（小声）”...总之，问问艾斯？

(以下全是ai写的，说是砖家会诊)

ChatGPT 也可能会犯错。请核查重要信息。
## ✨ 项目特点

* ✅ <b>我还是觉得没什么技术</b>，你可以非常容易的看懂我写了些什么
* ✅ 支持 QQ 官方开放平台事件推送 Webhook 接入
* ✅ 支持 OneBot v11/DeluxeBot WebSocket 客户端通信
* ✅ 自动处理 ID 映射，映射后的ID为数字ID
* ✅ 图床接口，QPS 0.6~1
* ✅ 支持多类型消息转发（文本、图片(base64/本地文件/远程url)、Ark 卡片、Markdown、表情(文本描述)、silk 语音(base64/本地文件/远程url)等）
* ✅ 基于MIT协议分发，高可配置
* ✅ 兼容 Gensokyo 迁移[教程](https://github.com/KelsAstell/Floodgate/tree/main/docs/export_bbolt/Export_Bbolt.md)(迁移数字id映射，不支持hash_id(仅支持数字ID迁移)，您可以自行修改数据库的创建代码，欢迎pr)
* ✅ 秒速启动，无需等待
* ✅ 支持兼容模式(默认模式，数字ID)或透传模式Alpha(⚠️OpenID透传需Bot自行适配哦)！

![启动耗时](https://pic1.imgdb.cn/item/685d117a58cb8da5c8738334.png)

## 💬 消息特性支持对比

> ✅：支持 | ❌：不支持 | ⚠️：部分支持或受限

| 消息类型       | OneBot v11 | DeluxeBOT | Floodgate | 说明                                                                                                    |
|------------|------------|-----------|-----------|-------------------------------------------------------------------------------------------------------|
| `文字`       | ✅          | ✅         | ✅         | 纯文本消息                                                                                                 |
| `图片`       | ✅          | ✅         | ✅         | 支持 base64、远程url与本地文件路径                                                                                |
| `图文混合`     | ✅          | ✅         | ✅         | 支持自动图文混排/队列上传（Floodgate 内部定义）                                                                         |
| `markdown` | ❌          | ✅         | ✅         | [支持 Markdown 透传，构造代码请看文档](https://github.com/KelsAstell/Floodgate/tree/main/docs/Markdown.md)         |
| `ark`      | ❌          | ✅         | ✅         | [支持 Ark 透传，构造代码请看文档](https://github.com/KelsAstell/Floodgate/tree/main/docs/Ark.md)                   |
| `成就`       | ❌          | ✅         | ✅         | [支持 Achievement 消息段，构造代码请看文档](https://github.com/KelsAstell/Floodgate/tree/main/docs/Achievement.md)       |
| `语音`       | ✅          | ✅         | ✅        | [支持 base64、远程url与本地文件路径传入的 silk，请看文档](https://github.com/KelsAstell/Floodgate/tree/main/docs/Silk.md) |
| `撤回`       | ✅          | ✅         | ✅         | [支持撤回群消息和私聊消息，请看文档](https://github.com/KelsAstell/Floodgate/tree/main/docs/Recall.md)                 |
| `表情`       | ✅          | ✅         | ✅         | 支持 显示表情文字                                                                                             |
| `视频`       | ✅          | ❌         | ❌         | 未实现该功能，可能不会开发                                                                                         |
| `文件`       | ✅          | ✅        | ❌         | 无开放平台接口对等能力                                                                                           |
| `at`       | ✅          | ❌         | ❌        | 无开放平台接口对等能力                                                                                           |
| `回复`       | ✅          | ❌         | ❌         | 无开放平台接口对等能力                                                                                           |
| `戳一戳`      | ✅          | ❌         | ❌         | 无开放平台接口对等能力                                                                                           |
| `位置`       | ✅          | ❌         | ❌         | 无开放平台接口对等能力                                                                                           |

| 特殊接口          | 描述                | 文档                                                                                       | OneBot v11 支持 | DeluxeBOT 支持 | Floodgate 支持 | 说明                                                            |
|---------------|-------------------|------------------------------------------------------------------------------------------|---------------|--------------|--------------|---------------------------------------------------------------|
| /upload_image | `图床`              | [阳光哥布林也能看懂的图床文档](https://github.com/KelsAstell/Floodgate/tree/main/docs/Upload_image.md) | ⚠️需自行适配       | ✅            | ✅            | DeluxeBOT特化代码，图床基于沙箱频道实现，<br/>本地缓存由DeluxeBOT内部实现，该功能需要开发者自行适配 |
| /user_stats   | `用户历史调用次数查询`      | FastAPI 已内置该接口文档                                                                         | ⚠️需自行适配       | ✅            | ✅            | 具有60秒缓存时间                                                     |
| /health       | `Floodgate 运行状态`  | FastAPI 已内置该接口文档                                                                         | ⚠️需自行适配       | ✅            | ✅           | GET接口，返回运行状态                                                  |
| /get_opid     | `从虚拟值获取openID` | 暂未开发，其实/avatar已经能获取到对应ID了                                                                | ⚠️需自行适配       | ✅            | ⚠️           | 开发中，懒x                                                        |
| /avatar       | `从虚拟值获取头像`        | FastAPI 已内置该接口文档                                                                         | ⚠️需自行适配       | ✅           | ✅           | GET接口，返回图片地址                                                  |


| 特性        | OneBot v11 支持 | DeluxeBOT 支持 | Floodgate 支持 | 说明                                                                              |
|-----------|---------------|--------------|--------------|---------------------------------------------------------------------------------|
| 消息去重      | ❌             | ✅            | ⚠️           | Floodgate支持同一业务ID的消息去重，<br/>但有时会收到不同业务ID，此时无法去重<br/>DeluxeBOT使用<b>没什么技术</b>进行去重 |
| 格式美化      | ❌             | ✅            | ✅            | 自动给群聊消息加个回车，很简单的QoL功能，<b>没什么技术吧</b>                                             |
| 消息并发      | ⚠️            | ✅            | ✅            | 性能也就那样，别指望uvicorn太多，<br/>50并行创建新用户档案不报错，你应用端顶得住就行                               |
| 入群event通知 | ✅             | ✅            | ✅            | 已实现标准notice                                                                     |
| 断联维护消息    | ❌似了怎么回复       | ✅            | ✅            | 已实现断联时回复维护消息                                                                    |
| 中间件内置命令   | ❌       | ✅            | ✅            | 内置命令文档施工中，现有命令：~health, ~offline, ~dau                                          |
| 事件日志      | ⚠️得用插件吧       | ✅            | ⚠️           | 开发中，基于用户的事件日志，为了快我不建议您开启这个功能，<br/>虽然我们有<b>没什么技术</b>的内存级别缓存                      |
| 服务升级      | ❌无法支持         | ⚠️暂未支持       | ⚠️           | 咕咕中，若识别到 DeluxeBOT 的请求头，且 Floodgate 与 DeluxeBOT 部署于同一台服务器，则优先使用 UNIX Socket     |



## 🏗 项目结构

```
Floodgate/
├── config.py                  # 配置文件（AppID、密钥、端口等）
├── run.py                    # 主程序入口
├── openapi/
│   ├── database.py           # 数据库
│   ├── encrypt.py            # 回调验证
│   ├── network.py            # 与开放平台交互核心
│   ├── parse_open_event.py   # QQ事件解析与转化
│   ├── token_manage.py       # access_token 管理
│   └── tool.py               # 工具函数（配置校验等）
```

## 🚀 启动方式

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

你可能需要依赖如 `fastapi`, `uvicorn`, `aiohttp`, `loguru`, `apscheduler` 等库。

### 2. 配置 `config.py`，把 `config_example.py` 改成 `config.py`

```python
BOT_SECRET = "你的 AppSecret"
BOT_APPID = 你的 AppID
PORT = 48443
WEBHOOK_ENDPOINT = "/floodgate"
WS_ENDPOINT = "/ws"
SANDBOX_MODE = False
```

### 3. 启动服务

```bash
python run.py
```
或者
```bash
没有或者，你自己写个bat也一样...
```

控制台将提示：

```shell
(一堆调试信息)
Floodgate已启动，耗时: X.XX 秒
```

超过一秒我吃...我啥也不吃

## 🔁 工作流程

### ✅ 从开放平台接收消息（Webhook）

开放平台回调地址设置为：

```
https://your-domain.com/floodgate
```

Floodgate 处理消息并转换为 OneBot v11 格式，通过 WebSocket 广播发送给已连接的客户端。

### ✅ 从 OneBot 客户端发送消息

OneBot 客户端通过 WebSocket 向 `/ws` 发送 `send_msg` 请求，Floodgate 会将其转为开放平台格式并调用 API 发送。

支持消息类型：

* 文本
* 富文本（图文混合）
* 图片（支持 base64、本地路径、网络 URL）
* Ark 卡片
* Markdown + 按钮
* Silk 音频 → 这个没测试

## 🧩 示例通信片段

### WebSocket 消息格式

OneBot 客户端发送标准通信包：

```json
{
  "action": "send_msg",
  "params": {
    "user_id": "123",
    "message": [
      {"type": "text", "data": {"text": "你好，Floodgate！"}}
    ]
  },
  "echo": "abc123"
}
```

Floodgate 会自动处理信息并发送到 QQ 官方接口。

## 🔒 安全性

* 签名验证机制按开放平台标准（详见 `encrypt.py`）
* 建议使用 HTTPS 进行公网部署，配合 nginx 配置反向代理

## ⚠ 注意事项

* **务必保管好你的 `AppSecret` 密钥**
* **默认端口为 48443，建议搭配 HTTPS 使用，您需要自行配置Nginx/Apache转发**
* 若 `MIGRATE_IDS = True`，请确保 `ids.json` 在同级目录，否则将自动跳过该流程

---

### 🗣️ 给开发者的真心话

**别让别人的愤怒压住了你的热情。<br>
我们相信你之所以写 bot，是因为你想要创造乐趣、传递想法、让别人眼前一亮。<br>
你不需要被羞辱式的开源去教育，不需要跪着说「谢谢大佬」，不需要因怕被嘲讽而删掉自己的创意，艾斯超级喜欢看到新东西！**

Floodgate 永远欢迎你——**只因为你有心写代码，有心创造，就值得被欢迎。**

我们认为：

> **一个真正优秀的开发者，应该被工具赋能，而不是被生态裹挟。**

我们痛惜看到部分开源环境中：

* 滥用「不技术即原罪」的态度对待用户；
* 拒绝协作与代码共享，却以「优越」姿态指责他人；
* 用非建设性的言论否定志愿者的贡献，甚至进行群体攻击或冷嘲热讽。

Floodgate 将始终**站在用户一边**，相信你可以选择最适合你的工具，**不需要「迎合谁」，只需热爱你想做的事。**

**去创造更多、有趣的内容吧！朋友，共勉。**

---

## 📜 License

MIT License - 你可以自由使用和修改此项目。
Copyright (c) 2025 KelsAstell

## 联系作者
* [GitHub](https://github.com/KelsAstell)
* [群聊] 478842113
