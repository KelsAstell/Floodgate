

# OneBot v11 Ark 消息发送文档（适用于 QQ 开放平台）

## 📦 背景说明

Ark 是 QQ 开放平台提供的一种结构化消息格式，允许开发者通过模板化方式发送包含标题、文本、链接等内容的卡片消息。通过 OneBot v11 协议发送 Ark 消息时，中间件（如 Floodgate）将其转换并透传给 QQ 开放平台。

---

## 📌 OneBot v11 Ark 消息发送示例

```python
await help_pic.finish(MessageSegment("ark", await assemble_ark(
    23,  # Ark 模板 ID（23 为新闻卡片模板）
    "帮助中心",  # 描述
    "帮助中心",  # 提示文本
    [
        {
            "text": f"{maiconfig.innerName}\n开发者：大以巴狼艾斯(机修狼狼)\n合作/咨询：xxxxx\n官方群：xxxxx"
        },
        {
            "text": "前往爱发电支持开发",
            "url": "https://afdi..."
        },
        {
            "text": "加入BOT官方交流群",
            "url": "https://qm.qq.com/cgi-bin/qm/qr?k=..."
        }
    ]
)))
```

---

## 🧱 `assemble_ark` 函数定义（实际实现）

```python
async def assemble_ark(template_id, desc, prompt, params: list):
    def parse_obj(obj_list):
        obj_data = []
        for obj in obj_list:
            if obj.get('url', None):
                obj_data.append({
                    "obj_kv": [
                        {"key": "desc", "value": f"{obj.get('text')}"},
                        {"key": "link", "value": f"{obj.get('url')}"}
                    ]
                })
            elif obj.get('text', None):
                obj_data.append({
                    "obj_kv": [
                        {"key": "desc", "value": f"{obj.get('text')}"}
                    ]
                })
        return obj_data

    if template_id == 23:
        return {
            "ark": {
                "template_id": 23,
                "kv": [
                    {"key": "#DESC#", "value": f"{desc}"},
                    {"key": "#PROMPT#", "value": f"{prompt}"},
                    {"key": "#LIST#", "obj": parse_obj(params)}
                ]
            }
        }
```

---

## 📤 Floodgate 中间件解析逻辑（Ark 消息处理）

```python
elif message.get("type") == "ark":
    payload = {
        "ark": message["ark"],
        "msg_type": 3,
        "msg_id": msg_id,
        "msg_seq": msg_seq
    }
    return await call_open_api(
        "POST",
        f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages",
        payload
    )
```

📌 **说明：**

* Ark 数据通过 `message["ark"]` 字段获取，保持结构一致即可正确透传；
* `msg_type=3` 表示 Ark 消息；
* 结构中 `ark.template_id=23` 适用于新闻类卡片。

---

## 🧾 示例中间件最终请求体

```json
{
  "msg_type": 3,
  "msg_id": 123456,
  "msg_seq": 1,
  "ark": {
    "template_id": 23,
    "kv": [
      { "key": "#DESC#", "value": "帮助中心" },
      { "key": "#PROMPT#", "value": "帮助中心" },
      {
        "key": "#LIST#",
        "obj": [
          {
            "obj_kv": [
              { "key": "desc", "value": "BOT 名称及开发者信息" }
            ]
          },
          {
            "obj_kv": [
              { "key": "desc", "value": "前往哔哩哔哩" },
              { "key": "link", "value": "https://example.com" }
            ]
          }
        ]
      }
    ]
  }
}
```

---

## ✅ 特性支持对比

| 特性         | OneBot v11 | DeluxeBOT | Floodgate 中间件 |
|------------|------------|-----------|---------------|
| `ark` 消息类型 | ⚠️非原生协议    | ✅         | ⚠️ 仅支持透传结构    |
| 多段卡片内容     | ❌          | ✅         | ❌             |
| 动态构造支持     | ❌          | ✅         | ❌             |

---

## ⚠️ 注意事项

* OneBotv11 并不原生支持 Ark 消息，需要使用上述构造代码构造 Ark 消息，并使用中间件将消息透传给 QQ 开放平台。
* 艾斯仅写了模板 ID `23` 的适配内容，其它模板需要开发者自行修改assemble_ark逻辑；
* 所有链接必须在开放平台备案，不备案发不出来；
* `desc`、`prompt` 以及 `#LIST#` 是必填字段，字段名必须完全匹配官方模板；
* 若中间件未能正确发送 Ark，请检查字段拼写与结构层级是否符合平台要求。

