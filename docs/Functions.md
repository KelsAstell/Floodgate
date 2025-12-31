
# ? Floodgate 增强功能说明文档

Floodgate 中间件除了实现标准 OneBot v11 接口外，还提供了多项增强能力，用于**优化与 QQ 官方开放平台的对接体验**，包括但不限于：**消息去重、格式美化、频道图床、断联提示、消息限速等**。以下为各增强功能的说明：

| 功能名称               | 默认启用 | 配置项                                                                        | 说明                                                                                |
|--------------------|------|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| **消息去重**           | ?    | 无                                                                          | 自动跳过重复 `message_id` 的事件，避免中间件或机器人二次处理同一消息。                                        |
| **消息重试**           | ?    | 无                                                                          | 消息上传失败时，尝试重新上传，最多尝试 3 次。                                                          |
| **格式美化**           | ?    | `ADD_RETURN`、`REMOVE_AT`                                                   | - `ADD_RETURN=True` 时，群聊文本前添加换行<br>- `REMOVE_AT=True` 时，移除 OneBot 转发中带入的 @机器人 内容。 |
| **频道图床**           | ?    | `SANDBOX_CHANNEL_ID`                                                       | 上传图片时若未指定频道 ID，会使用此默认频道发送图片用于图床功能。依赖 `/upload_image` 接口。                          |
| **断联提示**           | ?    | `MAINTAINING_MESSAGE`                                                      | 所有 OneBot 客户端断联时，中间件自动通过 `post_floodgate_message()` 回复维护中提示。                      |
| **消息速率控制**         | ?    | `RATE_LIMIT`、`MAX_MESSAGES`、`TIME_WINDOW_SECONDS`、`BLOCK_DURATION_SECONDS` | 防止用户刷屏，中间件级别判断用户发送频率，超出限制自动封禁一段时间（不发送至机器人）。                                       |
| **ID 映射系统（IDMAP）** | ?    | `IDMAP_INITIAL_ID`, `IDMAP_TTL`                                            | 用于对 QQ 的 OpenID 进行数字 ID 映射，保持 OneBot 兼容性。数字 ID 起始值及缓存时间可配置。                       |
| **Gensokyo ID 迁移** | ?    | `MIGRATE_IDS`                                                              | 是否迁移早期 Gensokyo 使用的 idmap 数据，默认关闭，仅供特定用户使用。                                       |
| **OpenID 透传模式**    | ?    | `TRANSPARENT_OPENID`                                                       | 启用后 OneBot 端将接收原始 OpenID（字符串格式），需 OneBot 实现自行适配，**不推荐普通用户开启**。                    |

---

## ? 说明细节（补充）

### ? 消息去重机制说明

Floodgate 会记录最近一段时间内处理过的消息 ID（`message_id`），并在重复出现时自动跳过处理逻辑。这样可以防止因网络重试或事件异常造成机器人重复响应。

---

### ? 消息格式美化

* `ADD_RETURN = True`：群聊文字前自动加 `\n`，避免 @ 内容与正文粘在一起，提升阅读体验。
* `REMOVE_AT = True`：在转发给 OpenAPI 前，移除OneBot原始消息中的 @(由 `at_sender=True` 添加)，防止重复触发指令。

---

### ? 图床支持

`/upload_image` 接口默认将图片发送至 `SANDBOX_CHANNEL_ID` 所指定频道，并返回其 URL 用于引用，实现简易的频道图床功能。

---

### ? 消息限速（中间件层）

该功能能**在机器人未被触发之前直接拦截消息**，是防刷机制的关键。

* 限制逻辑如下：

    * 某用户在 `TIME_WINDOW_SECONDS` 秒内发送消息超过 `MAX_MESSAGES` 条
    * 将其封禁 `BLOCK_DURATION_SECONDS` 秒
    * 封禁期间内新消息将收到提示，不会再推送到机器人
    * 若用户是管理员，则完全不进行记录，也不进行拦截

* 示例配置：

```python
RATE_LIMIT = True
MAX_MESSAGES = 6
TIME_WINDOW_SECONDS = 10
BLOCK_DURATION_SECONDS = 60
```

---

### ? IDMAP（OpenID → 数字 ID）

* OpenID 是 QQ 频道平台中的唯一身份标识，但与 OneBot 的数字 ID 不兼容。
* Floodgate 自动为每个 OpenID 分配唯一的数字 ID（从 `IDMAP_INITIAL_ID` 开始），以便于 OneBot 机器人使用。
* 分配映射缓存时间由 `IDMAP_TTL` 控制，单位为秒，缓存命中时不查询数据库。

---

### ? Gensokyo ID 迁移

如果你的机器人曾使用 Gensokyo 中间件，并且用的是最初的数字映射方案，**可启用 `MIGRATE_IDS = True` 自动迁移旧 ID 数据**。否则无需开启。
[相关工具及教程](https://github.com/KelsAstell/Floodgate/tree/main/docs/export_bbolt/Export_Bbolt.md)

---

### ? OpenID 透传模式（高级）

* 启用后，Floodgate 不再进行 ID 映射，而是直接将 OpenID 作为用户/群组 ID 传递给 OneBot。
* 需 OneBot 实现支持字符串 ID，否则会抛错或无法使用。
* 一般用于调试或自定义 Bot 开发者使用，默认不建议开启。
* 如果你的Bot真的支持的话...那或许不使用Floodgate中间件，而是hook其逻辑或者重写一份会更好？**Floodgate是基于MIT协议分发的，我没意见并且鼓励这样做。**

---

## ? 示例小节

若你当前配置如下：

```python
RATE_LIMIT = True
MAX_MESSAGES = 5
TIME_WINDOW_SECONDS = 10
BLOCK_DURATION_SECONDS = 60
```

则代表任意用户每 10 秒内最多允许发送 5 条消息，否则将自动禁言 60 秒，且期间不会触发任何机器人响应逻辑，节省处理成本。

~~闲得慌可以找个班上，而不是在那里刷我机器人的流量。你们赢了，真的是闲的蛋疼。~~
