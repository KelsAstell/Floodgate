import re
import time
from typing import Dict, Any, List

from config import BOT_APPID, TRANSPARENT_OPENID
from openapi.constant import face_id_dict
from openapi.database import get_or_create_digit_id
from anyio import Lock
from aiocache import Cache

# 创建缓存（内存缓存 + 5 分钟 TTL）
cache = Cache(Cache.MEMORY, ttl=300)

# 消息 ID 生成器类
class MessageIDGenerator:
    def __init__(self, start: int = 1):
        self._lock = Lock()
        self._current_id = start

    async def next(self) -> int:
        async with self._lock:
            message_id = self._current_id
            self._current_id += 1
            return message_id

# 实例化全局 ID 分配器
global_id_generator = MessageIDGenerator()


async def get_global_message_id() -> int:
    return global_id_generator._current_id

# open_id → message_id 映射，带生成
async def open_id_to_message_id(open_message_id: str, user_digit_id: int, group_digit_id: int) -> int:
    cache_key = f"open_to_num:{open_message_id}"
    existing_id = await cache.get(cache_key)
    if existing_id is not None:
        return existing_id

    # 使用线程安全的 ID 生成器，警钟敲烂
    current_id = await global_id_generator.next()
    await cache.set(cache_key, current_id)
    await cache.set(f"num_to_open:{user_digit_id}|{group_digit_id}", open_message_id)
    return current_id

# message_id → open_id 映射
async def message_id_to_open_id(user_digit_id: int, group_digit_id: int) -> str:
    return await cache.get(f"num_to_open:{user_digit_id}|{group_digit_id}")

def convert_openapi_message_to_cq(content: str, attachments: list) -> list:
    message = [{"type": "text", "data": {"text": content}}] if content else []
    for att in attachments:
        if att.get("content_type", "").startswith("image/") and att.get("url"):
            message.append({
                "type": "image",
                "data": {
                    "file": att["url"]
                }
            })
    return message

from typing import List, Dict, Any


def returnable_ark(data):
    # Onebot端实现应该是：MessageSegment("ark", {'ark': {...}})
    return {
        "type": "ark",
        "ark": data.get("ark")
    }

def returnable_markdown(data):
    # Onebot端实现应该是：MessageSegment("markdown", {"data": {'keyboard': {"id": "102097712_1736214096"}}})
    # 或者 MessageSegment("markdown", {"data": {'content':{...}, 'keyboard': {"id": "102097712_1736214096"}}})
    markdown_data = data.get("data")
    if "content" not in markdown_data:
        return {
            "type": "markdown_keyboard",
            "keyboard": markdown_data.get("keyboard")
        }
    return {
        "type": "markdown",
        "content": markdown_data.get("content"),
        "keyboard": markdown_data.get("keyboard")
    }

def returnable_achievement(data):
    return {
        "type": "achievement",
        "achievement_id": data.get("id"),
    }

def returnable_record(data):
    return {
        "type": "file",
        "file_type": 3,
        "data": data.get("file")
    }




# 立即返回的消息类型
RETURNABLE_SEGMENT_DICT = {
    "ark": returnable_ark,
    "markdown": returnable_markdown,
    "achievement": returnable_achievement,
    "record": returnable_record
}

def rich_segment_text(data, rich_segments, seg_type):
    text = data.get("text", "")
    if text:
        rich_segments.append({
            "type": "text",
            "text": text
        })
    return rich_segments

def rich_segment_image(data, rich_segments, seg_type):
    url = data.get("file") or data.get("url")
    if url:
        rich_segments.append({
            "type": "image",
            "url": url
        })
    return rich_segments

def rich_segment_face(data, rich_segments, seg_type):
    face_id = data.get("face_id")
    if face_id:
        rich_segments.append({
            "type": "text",
            "text": f"[表情：{face_id_dict.get(face_id)}]"
        })
    return rich_segments

def rich_segment_at(data, rich_segments, seg_type):
    #疑似 message_reference，但是官方文档显示暂未支持
    # user_id = data.get("qq")
    # if user_id:
    #     rich_segments.append({
    #         "type": "mention",
    #         "user_id": user_id
    #     })
    return rich_segments

def rich_segment_unknown(data, rich_segments, seg_type):
    rich_segments.append({
        "type": "text",
        "text": f"[UNKNOWN: {seg_type}]"
    })
    return rich_segments


# 富文本消息类型
RICH_TEXT_SEGMENT_DICT = {
    "text":rich_segment_text,
    "image":rich_segment_image,
    "face":rich_segment_face,
    "at":rich_segment_at,
}

def convert_cq_to_openapi_message(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    rich_segments = []
    for seg in segments:
        seg_type = seg.get("type")
        data = seg.get("data", {})
        if seg_type in RETURNABLE_SEGMENT_DICT:
            return RETURNABLE_SEGMENT_DICT[seg_type](data)
        rich_segments = RICH_TEXT_SEGMENT_DICT.get(seg_type, rich_segment_unknown)(data, rich_segments, seg_type)
    if len(rich_segments) == 1 and rich_segments[0]["type"] == "text":
        return {
            "type": "text",
            "text": rich_segments[0]["text"]
        }
    else:
        return {
            "type": "rich_text",
            "segments": rich_segments
        }

async def parse_group_add(payload: dict):
    if not TRANSPARENT_OPENID:
        return {
            "time": payload.get("timestamp"),
            "self_id": str(BOT_APPID),
            "post_type": "notice",
            "notice_type": "group_increase",
            "sub_type": "invite",
            "group_id": await get_or_create_digit_id(payload.get("group_openid")),
            "operator_id": 0,
            "user_id": await get_or_create_digit_id(payload.get("op_member_openid"))
        }
    return {
        "time": payload.get("timestamp"),
        "self_id": str(BOT_APPID),
        "post_type": "notice",
        "notice_type": "group_increase",
        "sub_type": "invite",
        "group_id": payload.get("group_openid"),
        "operator_id": 0,
        "user_id": payload.get("op_member_openid")
    }


async def parse_open_message_event(current_msg_id,payload: dict):
    user_open_id = payload.get("author", {}).get("union_openid")
    group_openid = payload.get("group_openid", payload.get("channel_id"))
    if not TRANSPARENT_OPENID:
        user_id = await get_or_create_digit_id(user_open_id)
        group_id = await get_or_create_digit_id(group_openid) if group_openid else None
    else:
        user_id = user_open_id
        group_id = group_openid
    open_msg_id = payload.get("id", "0")
    message_id = int(await open_id_to_message_id(open_msg_id,user_id, group_id))
    if current_msg_id >= message_id: # 消息去重
        return None
    timestamp = int(time.time())
    content_str = payload.get("content", "").strip()
    if payload.get("channel_id"):
        content_str = re.sub(r'<@![0-9A-Za-z]+>', '', content_str).strip()
    message = convert_openapi_message_to_cq(content_str, payload.get("attachments", []))
    event = {
        "time": timestamp,
        "self_id": str(BOT_APPID),
        "post_type": "message",
        "message_type": "group" if group_openid else "private",
        "sub_type": "normal",
        "message_id": message_id,
        "user_id": user_id,
        "message": message,
        "raw_message": payload.get("content", ""),
        "font": 0,
        "sender": {
            "user_id": user_id,
            "nickname": payload.get("author", {}).get("nickname", "") or "unknown",
            "card": "",
            "sex": "unknown",
            "age": 0,
            "area": "",
            "level": "",
            "role": "",
            "title": ""
        }
    }
    if group_openid:
        event["group_id"] = group_id
    return event