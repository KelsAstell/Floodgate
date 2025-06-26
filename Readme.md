# Floodgate

## 📚 目录

- [Floodgate](#floodgate)
- [🚫 Floodgate 不是什么](#-floodgate-不是什么)
- [✨ 项目特点](#-项目特点)
- [🏗 项目结构](#-项目结构)
- [🚀 启动方式](#-启动方式)
    - [1. 安装依赖](#1-安装依赖)
    - [2. 配置 configpy](#2-配置-configpy)
    - [3. 启动服务](#3-启动服务)
- [🔁 工作流程](#-工作流程)
    - [✅ 从开放平台接收消息（Webhook）](#✅-从开放平台接收消息webhook)
    - [✅ 从 OneBot 客户端发送消息](#✅-从-onebot-客户端发送消息)
- [🧩 示例通信片段](#-示例通信片段)
    - [WebSocket 消息格式](#websocket-消息格式)
- [🔒 安全性](#-安全性)
- [⚠ 注意事项](#-注意事项)
- [📜 License](#-license)
- [联系作者](#联系作者)


## 🚫 Floodgate 不是什么

请注意，**Floodgate 不是一个通用的 OneBot 实现**。它并非旨在兼容所有 OneBot 客户端或完整实现 OneBot v11 协议的全部特性。

Floodgate 是一个为 **DeluxeBOT** 特化设计的类 OneBot-QQ 协议转换中间件，它的构建目标是服务于特定工作流，而不是通用适配。

* ❌ 它**不支持所有 OneBot 扩展或插件功能**
* ❌ 它**不会支持未在 DeluxeBOT 场景中使用的协议行为**
* ❌ 它**不会主动对协议做泛化适配**

某些你期待的功能如果“**艾斯不会用到**”，那就很可能“**不会做**”。


#### Floodgate 是一个桥接 [QQ 机器人开放平台](https://bot.q.qq.com/) 和 [OneBot v11](https://onebot.dev/) 协议的中间件框架，支持通过 Webhook 接收事件并将其转发至 OneBot 客户端，同时反向接收 OneBot 消息并调用开放平台 API 进行转发，实现机器人协议兼容与灵活扩展。
(以下全是ai写的)
## ✨ 项目特点

* ✅ 支持 QQ 官方开放平台事件推送 Webhook 接入
* ✅ 支持 OneBot v11/DeluxeBot WebSocket 客户端通信
* ✅ 没什么技术
* ✅ 自动处理 ID 映射，映射后的ID为数字ID
* ✅ 图床接口，QPS 0.6~1
* ✅ 支持多类型消息转发（文本、Base64图片、图片直链、本地图片、Ark 卡片、Markdown、表情(只渲染文本描述)、Silk 语音(base64格式)等）
* ✅ 高可配置，兼容 Gensokyo 迁移(仅支持数字id映射，不支持idmap_pro，您可以自行修改数据库的创建代码，欢迎pr)
* ✅ 秒速启动，无需等待

![启动耗时](https://pic1.imgdb.cn/item/685d117a58cb8da5c8738334.png)

## 💬 消息特性支持对比

> ✅：支持 | ❌：不支持 | ⚠️：部分支持或受限

| 消息类型       | OneBot v11 | DeluxeBOT | Floodgate | 说明                            |
|------------|------------|-----------|-----------|-------------------------------|
| `文字`       | ✅          | ✅         | ✅         | 纯文本消息                         |
| `图片`       | ✅          | ✅         | ✅         | 支持 base64、URL、本地路径            |
| `图文混合`     | ✅          | ✅         | ✅         | 支持自动图文混排/队列上传（Floodgate 内部定义） |
| `markdown` | ❌          | ✅         | ✅         | 支持开放平台 markdown 结构            |
| `ark`      | ❌          | ✅         | ✅         | 支持 Ark 卡片结构                   |
| `语音`       | ❌          | ❌         | ⚠️        | 仅支持 base64 silk，未测试           |
| `撤回`       | ✅          | ❌         | ❌         | 未实现该功能，开发中                    |
| `表情`       | ✅          | ❌         | ❌         | 未实现该功能，开发中                    |
| `视频`       | ✅          | ❌         | ❌         | 未实现该功能，可能不会开发                 |
| `文件`       | ✅          | ⚠️        | ❌         | 不支持泛文件上传                      |
| `at`       | ✅          | ❌         | ⚠️        | 无开放平台接口对等能力                   |
| `回复`       | ✅          | ❌         | ❌         | 无开放平台接口对等能力                   |
| `戳一戳`      | ✅          | ❌         | ❌         | 无开放平台接口对等能力                   |
| `位置`       | ✅          | ❌         | ❌         | 无开放平台接口对等能力                   |

| 特殊接口                 | 描述                | OneBot v11 支持 | DeluxeBOT 支持 | Floodgate 支持 | 说明                                                          |
|----------------------|-------------------|---------------|--------------|--------------|-------------------------------------------------------------|
| /upload_base64_image | `图床及本地数据缓存`       | ⚠️需自行适配       | ✅            | ✅            | DeluxeBOT特化代码，图床基于测试频道实现，<br/>本地缓存由DeluxeBOT实现，该功能需要开发者自行适配 |
| /user_stats          | `用户历史调用次数查询`      | ⚠️需自行适配       | ✅            | ⚠️           | 开发中                                                         |
| /health              | `Floodgate 运行状态`  | ⚠️需自行适配       | ✅            | ⚠️           | 开发中                                                         |
| /get_opid            | `从虚拟值获取唯一 openID` | ⚠️需自行适配       | ✅            | ⚠️           | 开发中                                                         |
| /avatar              | `从虚拟值获取头像`        | ⚠️需自行适配       | ⚠️           | ⚠️           | 开发中                                                         |


| 特性        | OneBot v11 支持 | DeluxeBOT 支持 | Floodgate 支持 | 说明                                                |
|-----------|---------------|--------------|--------------|---------------------------------------------------|
| 消息去重      | ❌             | ✅            | ⚠️           | Floodgate支持同一业务ID的消息去重，<br/>但有时会收到不同业务ID，此时无法去重   |
| 格式美化      | ❌             | ✅            | ✅            | 自动给群聊消息加个回车，很简单的QoL功能，<b>没什么技术吧</b>               |
| 消息并发      | ⚠️            | ✅            | ✅            | 性能也就那样，别指望uvicorn太多，<br/>50并行创建新用户档案不报错，你应用端顶得住就行 |
| 入群event通知 | ✅             | ✅            | ⚠️           | 开发中，现在会发送一个空消息事件                                  |
| 事件日志      | ⚠️你得用插件吧      | ✅            | ⚠️           | 开发中，基于用户的事件日志                                     |



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
* **默认端口为 48443，建议搭配 HTTPS 使用**
* 若 `MIGRATE_IDS = True`，请确保 `ids.json` 在同级目录，否则将自动跳过该流程

## 📜 License

MIT License - 你可以自由使用和修改此项目。
Copyright (c) 2025 KelsAstell

## 联系作者
* [GitHub](https://github.com/KelsAstell)
