# 消息撤回功能文档（OneBot v11 + Floodgate）

本功能允许通过 OneBot v11 `bot.delete_msg` 动作调用，实现撤回已发送的消息，并通过 Floodgate 中间件转译为 QQ 开放平台 API 的消息删除请求。

---

## 发送与撤回消息示例（Onebot11 端）

```python
# 发送消息
ret = await about_me.send(
    f"兽太发送了一条消息，现在要尝试使用floodgate中间件撤回它咯", at_sender=True
)
msg_id = ret.get("message_id")

# 撤回消息
if msg_id:
    if isinstance(event, GroupMessageEvent):
        await bot.delete_msg(message_id=msg_id, group_id=event.group_id)
    else:
        await bot.delete_msg(message_id=msg_id, user_id=event.get_user_id())
```

---

## Floodgate 中间件处理逻辑

### WebSocket 接收 OneBot 请求：

```python
if message.get("action") == "delete_msg":
    message_id = message["params"].get("message_id")
    if message_id:
        await delete_im_message(
            message["params"].get("user_id"),
            message["params"].get("group_id"),
            message_id
        )
        await websocket.send_json({
            "status": "ok",
            "retcode": 0,
            "data": {},
            "echo": message["echo"]
        })
```

### 自动判断撤回对象（群 or 私聊）：

```python
async def delete_im_message(user_digit_id, group_digit_id, message_id):
    endpoint = "/v2/groups" if group_digit_id else "/v2/users"
    digit_id = group_digit_id if group_digit_id else user_digit_id
    return await call_open_api(
        "DELETE",
        f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages/{message_id}?hidetip=true",
        None
    )
```

---

## 注意事项

* `message_id` 应为发送接口返回的 `id` 字段；该字段为OpenAPI的标准msg_id，极大的减少了Floodgate中间件的转换逻辑。
* 若为群聊消息需传 `group_id`，私聊传 `user_id`；
* QQ 开放平台接口权限需包含 `messages.write`；
* 本实现基于 WebSocket 与 OneBot v11 的 `delete_msg` 标准动作。
