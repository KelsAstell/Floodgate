
# ? OneBot v11 `audio` 消息发送文档（群聊/私聊 Silk 音频）

## ? 功能概述

使用 OneBot v11 的 `record` 消息段（类型为 `audio`），可以向 QQ 的**群聊或私聊**发送 `.silk` 格式语音消息。Floodgate 中间件会识别 base64 格式的数据，转码并通过 QQ 官方 API（私域）上传语音文件。

---

## ? OneBot v11 示例代码

```python
import base64
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment, MessageEvent

send_dummy_silk = on_command("发语音")

@send_dummy_silk.handle()
async def _(event: MessageEvent):
    try:
        with open(r"E:\DeluxeBOT\testbot\test.silk", "rb") as f:
            silk_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"Failed to encode silk audio: {e}")
        await send_dummy_silk.finish("silk编码失败", reply_message=True)

    # 这样发送    
    await send_dummy_silk.finish(MessageSegment.record(f"base64://{silk_base64}"))
    # 或者..
    await send_dummy_silk.finish(MessageSegment.record(r"file:///E:\DeluxeBOT\testbot\test.silk"))
    # 还可以..
    await send_dummy_silk.finish(MessageSegment.record(f"https://your-website.com/test.silk"))
```

---

## ? 消息段说明

| 消息段类型    | 字段名  | 值格式               | 说明                                      |
| -------- | ---- |-------------------|-----------------------------------------|
| `record` | file | `base64://...` 或 `http(s)://...`或 `file:///...` | base64 编码的 `.silk` 音频，或远程直链 URL，或本地文件路径 |

---

## ? Floodgate 中间件处理简述

1. 判断消息段类型为 `record`；
2. 若 `file` 字段以 `base64://` 开头：

    * 截取 base64 内容；
    * 解码为二进制 `.silk`；
    * 通过 QQ 接口（群/私聊消息）上传为语音；
3. 若 `file` 字段以 `http(s)://...` 开头：
    * 尝试获取链接
    * 通过 QQ 接口（群/私聊消息）上传为语音；

4. 上传成功后自动替换为可识别的语音消息格式发送。

---

## ? 支持与限制说明

| 特性项      | 状态    | 说明                  |
|----------|-------|---------------------|
| 群聊语音支持   | ? 支持  | 可直接使用 record 段发至群聊  |
| 私聊语音支持   | ? 支持  | 可直接使用 record 段发至私聊  |
| 远程语音 URL | ? 支持  | 音频文件需公网可访问          |
| 文件路径语音   | ?? 支持 | 需同机部署Ob11和Floodgate |


---

## ? 注意事项

* `.silk` 文件需符合 QQ 要求：16kHz 单声道、最大 60s；
* base64 长度不应超过 1MB，建议限制在 60 秒内的语音；
* 若发送失败（如富媒体格式错误），Floodgate 应提供报错日志；
* 请勿直接发送 mp3/wav，需转换为 QQ 支持的 `.silk` 格式。(自动转换功能未来拟通过新的消息段类型实现)

---

## ? 可选工具推荐

如需将常见音频格式（如 mp3、wav）转换为 silk，可使用：

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 -f s16le -acodec pcm_s16le raw.pcm
silk_v3_encoder raw.pcm output.silk -tencent
```
