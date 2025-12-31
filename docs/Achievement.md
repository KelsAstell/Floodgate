
---

# 🏆 Achievement 成就系统

Floodgate 内置了一个轻量、可扩展的成就系统，支持通过 OneBot v11 消息触发展示成就，并生成精美图片发送到 QQ 官方频道或私聊中。

---

## 📌 功能概览

* ✅ 支持 OneBot v11 使用 `achievement` 自定义消息段触发
* ✅ 成就数据本地定义，含 `title`、`description`、`rarity` 等字段
* ✅ 自动生成带有图文信息的成就图片
* ✅ 同一成就只触发一次，支持持久化判重
* ✅ 支持分页浏览已获得成就列表

---

## 📤 OneBot v11 调用方式

使用 OneBot 消息段(已实现)：

```python
await bot.send(MessageSegment("achievement", {"id": 3}))
//或者..
await event.send(MessageSegment("achievement", {"id": 3}))
```

或发送 JSON 格式的消息段(未经测试)：

```json
{"type": "achievement", "data": {"id": 3}}
```

---

## 🔧 Floodgate 端逻辑说明

### 1. 消息段解析

```python
elif seg_type == "achievement":
    return {
        "type": "achievement",
        "achievement_id": data.get("id"),
    }
```

### 2. 成就触发处理

```python
elif message.get("type") == "achievement":
    ach_id = message.get("achievement_id")
    is_new = await add_achievement(user_id, ach_id)
    if not is_new:
        return {"msg": "User have already got this achievement"}

    file_data = await generate_achievement_image(ach_id)
    payload = {"file_type": 1, "file_data": file_data}
    ret = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
    ...
```

---

## 🗃 成就数据结构

在配置中定义两个核心结构：

```python
ACHIEVEMENT_IDMAP = {
    1: "10/102339",  # 示例：图像路径，为mcmod的图标路径，会缓存到本地
    2: "82/820265"
}

ACHIEVEMENT_DATA = {
    1: {
        "id": 1,
        "title": "时神的礼物",
        "description": "使用超级丝瓜卡",
        "rarity": "epic"
    },
    2: {
        "id": 2,
        "title": "冒险，于薄暮启程",
        "description": "4点半前游玩福瑞大冒险",
        "rarity": "epic",
        "mask": True  # 可用于遮罩成就达成条件，可选参数
    }
}
```

字段说明：

| 字段名           | 类型   | 说明                                  |
| ------------- | ---- |-------------------------------------|
| `id`          | int  | 成就 ID（唯一）                           |
| `title`       | str  | 成就名称                                |
| `description` | str  | 描述文字                                |
| `rarity`      | str  | 稀有度（如 common, uncommon, rare, epic） |
| `mask`        | bool | 是否应用遮罩（可选）                          |

---

## 📖 查看成就列表

用户可通过命令查看自己的成就：

```
~成就         # 查看第 1 页
~成就 2       # 查看第 2 页
```

Floodgate 会：

* 调用 `get_achievement_list` 获取用户成就；
* 调用 `generate_achievement_page_image` 生成分页图片；
* 使用富媒体消息发送图文。

---

## ⚠ 注意事项

* 所有成就 ID 必须在 `ACHIEVEMENT_DATA` 中注册；
* 如启用 `ACHIEVEMENT_PERSIST = True`，Floodgate将持久化记录用户已获成就，无需Onebot端手动管理成就触发状态；
* 若未启用 `ACHIEVEMENT_PERSIST`，则Floodgate不进行任何数据库操作，若Onebot端未能正确管理成就，可能造成重复触发；

---
