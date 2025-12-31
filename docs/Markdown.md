
# OneBot v11 Markdown 消息发送文档（适用于 QQ 开放平台）

## 📦 背景说明

QQ 开放平台支持发送带按钮的 **Markdown 消息**，这类结构化消息适合用于呈现复杂内容（如标题、链接、加粗、引用等）并附带互动操作按钮。通过 OneBot v11，可以将这类消息结构构造成标准消息段并由中间件转译。

⚠️ **注意：单独发送按钮的机器人需为金牌（≥2000 DAU）才能成功发送 keyboard-only 消息。**

---

## 📌 OneBot v11 示例代码

最基本的 Markdown 消息段构造如下：

```python
# 发送 Markdown 模板消息（推荐格式）
await pic_mrjm.finish(MessageSegment("markdown", {
    "content": {
        "custom_template_id": "102097712_1716317267",
        "params": [
            {"key": "title", "values": ["标题内容"]},
            {"key": "desc", "values": ["描述内容"]}
        ]
    }
}))

# 发送带按钮的 Markdown 消息
await bot.send(MessageSegment("markdown", {
    "content": {
        "custom_template_id": "102097712_1716317267",
        "params": [...]
    },
    "keyboard": {
        "id": "1000000_100000000"
    }
}))

# 仅发送按钮（已失效）
await bot.send(MessageSegment("markdown", {
    "keyboard": {
        "id": "1000000_100000000"
    }
}))
```

---

## 🧱 数据结构说明（MessageSegment）

| 字段名        | 类型   | 是否必须 | 说明                               |
| ---------- | ---- | ---- |----------------------------------|
| `content`  | dict | ❌  | Markdown 模板内容，包含 `custom_template_id` 和 `params`（若为空则仅发送按钮，需要2000DAU） |
| `keyboard` | dict | ❌    | 按钮面板 ID，格式为 `{"id": "xxx_xxx"}`          |

### content 字段结构

| 字段名        | 类型   | 是否必须 | 说明                               |
| ---------- | ---- | ---- |----------------------------------|
| `custom_template_id`  | str | ✅  | QQ 控制台配置的 Markdown 模板 ID |
| `params` | list | ✅    | 模板参数列表，每个参数包含 `key` 和 `values` 字段 |

---

## 🧰 Floodgate 中间件解析逻辑（伪代码）

```python
elif seg_type == "markdown":
    # 客户端发送: MessageSegment("markdown", {"content": {...}, "keyboard": {...}})
    # WebSocket消息: {"type": "markdown", "data": {"content": {...}, "keyboard": {...}}}
    markdown_data = data.get("data")
    if markdown_data is None:
        markdown_data = data  # 兼容直接传递的情况
    
    content = markdown_data.get("content")
    keyboard = markdown_data.get("keyboard")
    
    # 如果只有keyboard没有content，返回markdown_keyboard类型
    if keyboard and not content:
        return {
            "type": "markdown_keyboard",  # 仅按钮
            "keyboard": keyboard
        }
    
    # 返回完整的markdown消息
    return {
        "type": "markdown",              # Markdown 模板 + 按钮（可选）
        "content": content,  # 包含 custom_template_id 和 params
        "keyboard": keyboard
    }
```

📌 **解释：**

* `content` 缺省 → 只发送按钮（需金牌机器人）；
* 存在 `content` → Markdown 模板消息，可选附带按钮；
* `content` 包含 `custom_template_id`（模板ID）和 `params`（参数列表）。

---

## 📤 最终中间件发送结构（发往 QQ 开放平台）

```json
{
  "msg_type": 2,
  "msg_id": 123456,
  "msg_seq": 1,
  "content": "markdown",  // 固定字段，表示为 Markdown 消息
  "keyboard": {           // 可选，有则添加
    "id": "1000000_100000000"
  },
  "markdown": {           // 可选，从 content 字段获取
    "custom_template_id": "102097712_1716317267",
    "params": [
      {"key": "title", "values": ["标题内容"]},
      {"key": "desc", "values": ["描述内容"]},
      {"key": "image_url", "values": ["https://example.com/image.jpg"]}
    ]
  }
}
```

---

## ✅ 特性支持对比

| 特性            | OneBot v11 | DeluxeBOT | Floodgate 中间件 |
| ------------- | ---------- |----------| ------------- |
| Markdown 正文支持 | ❌        | ✅       | ✅           |
| Keyboard 支持   | ❌        | ✅     | ✅           |
| 仅按钮（无正文）支持    | ❌        | ✅   | ✅           |

---

## ⚠️ 注意事项

* `keyboard.id` 是唯一标识按钮面板的 ID，需在 QQ 控制台配置；
* `content` 可省略，但若省略则需满足 QQ 对**DAU**（日活≥2000）要求，否则会报错；
* `custom_template_id` 需要在 QQ 控制台预先创建并配置 Markdown 模板；
* `params` 中的 `key` 必须与模板中定义的占位符一致；
* 建议分开发送普通文字与 Markdown 消息，**不要将 Markdown 与 text 混合成一条消息段**（中间件已阻止此行为）。

## 📝 完整示例

```python
# DeluxeBOT 实际使用示例
await help_pic.send(MessageSegment("markdown", {
    "content": {
        "custom_template_id": "102097712_1716317267",
        "params": [
            {"key": "usage", "values": ["好多"]},
            {"key": "version", "values": ["1.5.2"]},
            {"key": "image_url", "values": ["https://deluxebot.wingmark.cn/deluxe/help_1.jpg"]},
            {"key": "credits", "values": ["翎迹天算、绿洲宇宙"]}
        ]
    }
}))
```

