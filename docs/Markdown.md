
# OneBot v11 Markdown 消息发送文档（适用于 QQ 开放平台）

## 📦 背景说明

QQ 开放平台支持发送带按钮的 **Markdown 消息**，这类结构化消息适合用于呈现复杂内容（如标题、链接、加粗、引用等）并附带互动操作按钮。通过 OneBot v11，可以将这类消息结构构造成标准消息段并由中间件转译。

⚠️ **注意：单独发送按钮的机器人需为金牌（≥2000 DAU）才能成功发送 keyboard-only 消息。**

---

## 📌 OneBot v11 示例代码

最基本的 Markdown 消息段构造如下：

```python
await pic_mrjm.finish(MessageSegment("markdown", {
    "data": {
        "keyboard": {
            "id": "1000000_100000000"
        },
        "content": {
            # markdown内容结构填充
        }
    }
}))
```

---

## 🧱 数据结构说明（MessageSegment）

| 字段名        | 类型   | 是否必须 | 说明                               |
| ---------- | ---- | ---- |----------------------------------|
| `keyboard` | dict | ✅    | 按钮面板 ID，格式为 `"xxx_xxx"`          |
| `content`  | dict | ❌  | Markdown 内容（若为空则仅发送按钮，需要2000DAU） |

---

## 🧰 Floodgate 中间件解析逻辑（伪代码）

```python
elif seg_type == "markdown":
    markdown_data = data.get("data")
    if "content" not in markdown_data:
        return {
            "type": "markdown_keyboard",  # 仅按钮
            "keyboard": markdown_data.get("keyboard")
        }
    return {
        "type": "markdown",              # 按钮 + Markdown 正文
        "content": markdown_data.get("content"),
        "keyboard": markdown_data.get("keyboard")
    }
```

📌 **解释：**

* `content` 缺省 → 只发送按钮（需金牌机器人）；
* 存在 `content` → 正常 Markdown 正文 + 按钮卡片一起发送；
* `content` 可为嵌套结构（含标题、列表、图片、链接等）。

---

## 📤 最终中间件发送结构（发往 QQ 开放平台）

```json
{
  "msg_type": 2,
  "msg_id": 123456,
  "msg_seq": 1,
  "content": "markdown",  // 固定字段，表示为 Markdown 消息
  "keyboard": {
    "id": "1000000_100000000"
  },
  "markdown": {
    // markdown结构化内容
    "title": "标题",
    "content": "**加粗内容**\n[链接文字](https://example.com)"
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
* `content` 可省略，但若省略则需满足 QQ 对**DAU**（日活）要求，否则会报错；
* Markdown 内容推荐使用平台支持的语法（如标题、加粗、链接、分割线）；
* 建议分开发送普通文字与 Markdown 消息，**不要将 Markdown 与 text 混合成一条消息段**（中间件已阻止此行为）。

