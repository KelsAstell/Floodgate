import base64
import hashlib
import json
from io import BytesIO
from typing import Optional

import aiohttp
import asyncio
from cachetools import TTLCache
from fastapi import HTTPException

from config import *
from openapi.database import get_union_id_by_digit_id, increment_usage, add_achievement
from openapi.draw_ach import generate_achievement_image
from openapi.parse_open_event import message_id_to_open_id
from openapi.token_manage import token_manager

msg_seq_cache = TTLCache(maxsize=SEQ_CACHE_SIZE, ttl=300)
# 异步锁，防止并发问题
cache_lock = asyncio.Lock()

SEND_FAILED_DICT = {"success":0, "failed":0}

async def get_send_failed_count() -> dict:
    return SEND_FAILED_DICT


async def get_next_msg_seq(msg_id: str) -> int:
    async with cache_lock:
        current = msg_seq_cache.get(msg_id, 0)
        current += 1
        msg_seq_cache[msg_id] = current
        return current


# 获取已弃用的wss地址，建议尽快迁移到webhook..我也没做对应的支持
async def get_wss_gateway(access_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"QQBot {access_token}"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(QQ_API_BASE + '/gateway', headers=headers, ssl=False) as response:
                if response.status == 200:
                    data = await response.json()
                    wss_url = data.get("url")
                    if wss_url:
                        log.success(f"成功获取 WSS 地址:{wss_url}")
                        return wss_url
                    else:
                        log.error("响应中缺少 'url' 字段")
                else:
                    error_text = await response.text()
                    log.error(f"请求失败，状态码: {response.status}, 错误信息: {error_text}")
        except aiohttp.ClientError as e:
            log.error(f"网络请求异常: {e}")


async def call_open_api(method: str, endpoint: str, payload: dict = None, sleepy:Optional[bool]=True):
    access_token = await token_manager.get_access_token(only_get_token=True)
    if not access_token:
        raise ValueError("无法获取 ACCESS_TOKEN，请尝试重启Floodgate")

    url = QQ_API_BASE + endpoint
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"QQBot {access_token}"
    }
    await asyncio.sleep(int(NAP_MILLSECONDS)/1000) if NAP_MILLSECONDS > 0 and sleepy else None
    async with aiohttp.ClientSession() as session:
        retries = 3
        for attempt in range(retries):
            try:
                log.debug(f"正在请求: {method} {url}, Headers: {headers}, Body: {payload}")
                async with session.request(
                        method=method,
                        url=url,
                        json=payload,
                        headers=headers,
                        ssl=False
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if attempt > 0:
                            log.success(f"第 {attempt} 次重试成功")
                            SEND_FAILED_DICT["success"] += 1
                        log.debug(f"请求成功: {method} {url}, 响应: {data}")
                        return data
                    else:
                        error_text = await response.text()
                        # 打印错误信息..有点吵，我先给注释了，这个bug奇奇怪怪的，总之重发能解决
                        # log.error(f"请求失败: {method} {url}, 状态码: {response.status}, 错误信息: {error_text}")
                        log.debug(f"payload: {json.dumps(payload, ensure_ascii=False)[:300]}")
                        if attempt < retries - 1:
                            await asyncio.sleep(1)
                            log.warning(f"第 {attempt + 1} 次重试...")
                            continue
                        else:
                            SEND_FAILED_DICT["failed"] += 1
                            raise HTTPException(status_code=response.status, detail=error_text)
            except Exception as e:
                log.warning(f"网络请求异常: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                    log.warning(f"第 {attempt + 1} 次重试...")
                    continue
                else:
                    raise HTTPException(status_code=503, detail=f"请求OpenAPI时出现异常: {e}")


async def post_guild_image(data):
    base64_image = data.get("base64_image", "")
    file_image = data.get("file_image", "")
    if not base64_image and not file_image:
        return {"error": "Param 'base64_image' or 'file_image' is required"}
    channel_id = data.get("channel_id", SANDBOX_CHANNEL_ID)
    if channel_id == 0:
        return {"error": "'channel_id' is required"}
    access_token = await token_manager.get_access_token(only_get_token=True)
    if not access_token:
        return {"error": "Failed to get ACCESS_TOKEN"}
    # 根据参数选择图片数据来源，支持文件直读
    if base64_image:
        image_data = base64.b64decode(base64_image)
    elif file_image:
        try:
            if file_image.startswith("file:///"):
                file_image = file_image.lstrip("file:///")
            with open(file_image, "rb") as f:
                image_data = f.read()
        except (IOError, FileNotFoundError) as e:
            log.error(f"文件读取失败: {e}")
            return {"error": "文件读取失败，请确认 file_image 参数是否正确"}
    url = f"https://api.sgroup.qq.com/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"QQBot {access_token}"
    }
    form = aiohttp.FormData()
    form.add_field(
        name="file_image",
        value=BytesIO(image_data),
        filename="image.jpg",
        content_type="image/jpeg"
    )
    form.add_field(
        name="msg_id",
        value="1024"
    )
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, data=form, ssl=False, timeout=10.0) as response:
                if response.status == 200:
                    data = await response.json()
                    log.debug(f"图片上传成功: {data}")
                    md5_hash = hashlib.md5(image_data).hexdigest().upper()
                    image_url = f"https://gchat.qpic.cn/qmeetpic/0/0-0-{md5_hash}/0"
                    return {"url": image_url}
                else:
                    text = await response.text()
                    log.error(f"Image uploaded failed: {text}")
                    return {"error": text}
        except Exception as e:
            log.error(f"Image uploaded failed: {e}")
            return {"error": f"Upload failed: {e}"}


async def post_floodgate_message(msg, d):
    user_openid = d.get("author", {}).get("union_openid")
    group_openid = d.get("group_openid",d.get("channel_id"))
    if group_openid:
        union_id = group_openid
        if str(group_openid).isdigit():
            endpoint = "/channels"
        else:
            msg = "\n" +  msg
            endpoint = "/v2/groups"
    else:
        endpoint = "/v2/users"
        union_id = user_openid
    msg_id = d.get("id", "0")
    return await call_open_api("POST", f"{endpoint}/{union_id}/messages", {"content": msg, "msg_type": 0, "msg_id": msg_id,"msg_seq": await get_next_msg_seq(msg_id)}, False)

async def post_floodgate_rich_message(msg, image, d):
    user_openid = d.get("author", {}).get("union_openid")
    group_openid = d.get("group_openid",d.get("channel_id"))
    if group_openid:
        union_id = group_openid
        if str(group_openid).isdigit():
            endpoint = "/channels"
        else:
            msg = "\n" +  msg
            endpoint = "/v2/groups"
    else:
        endpoint = "/v2/users"
        union_id = user_openid
    payload = {"file_type": 1, "file_data": image}
    ret = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
    image_info = ret["file_info"]
    msg_id = d.get("id", "0")
    payload = {"content": msg, "msg_type": 7, "media": {"file_info": image_info}, "msg_id": msg_id,
               "msg_seq": await get_next_msg_seq(msg_id)}
    return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload, False)

async def post_im_message(user_id, group_id, message):
    msg_id = await message_id_to_open_id(user_id, group_id)
    msg_seq = await get_next_msg_seq(msg_id)
    endpoint = "/v2/groups" if group_id else "/v2/users"
    id = group_id if group_id else user_id
    union_id = id if TRANSPARENT_OPENID else await get_union_id_by_digit_id(id)
    if str(union_id).isdigit():
        endpoint = "/channels"
    await increment_usage(user_id)
    if message.get("type") == "text":
        payload = {"msg_type": 0, "msg_id": msg_id, "msg_seq": msg_seq}
        if group_id and ADD_RETURN and not message["text"].startswith("\n"):
            payload["content"] = "\n" + message["text"]
        else:
            payload["content"] = message["text"]
        return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload)
    elif message.get("type") == "rich_text":
        segments = message["segments"]
        image_info_list = []
        text = ""
        for segment in segments:
            if segment["type"] == "text":
                text += segment["text"]
            elif segment["type"] == "image":
                if segment["url"].startswith("base64://"):
                    payload = {"file_type": 1, "file_data": segment["url"][9:]}
                    ret = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("http://") or segment["url"].startswith("https://"):
                    payload = {"event_id": msg_id, "file_type": 1, "url": segment["url"]}
                    ret = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("file:///"):
                    file_path = segment["url"].lstrip("file:///")
                    with open(file_path, "rb") as image_file:
                        encoded_str = base64.b64encode(image_file.read()).decode("utf-8")
                        payload = {"file_type": 1, "file_data": encoded_str}
                        ret = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
                        image_info_list.append(ret["file_info"])
        if len(image_info_list) > 1:
            for image in image_info_list[:-1]:
                payload = {"msg_type": 7, "media": {"file_info": image}, "msg_id": msg_id,
                           "msg_seq": await get_next_msg_seq(msg_id)}
                await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload)
        if not len(image_info_list):
            payload = {"content": text, "msg_type": 0, "msg_id": msg_id, "msg_seq": await get_next_msg_seq(msg_id)}
            sleepy = False
        else:
            payload = {"content": text, "msg_type": 7, "media": {"file_info": image_info_list[-1]}, "msg_id": msg_id,
                       "msg_seq": await get_next_msg_seq(msg_id)}
            sleepy = True
        if group_id and ADD_RETURN and not payload["content"].startswith("\n"):
            if payload["content"]:
                payload["content"] = "\n" + payload["content"]
        return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload, sleepy)
    elif message.get("type") == "ark":
        payload = {"ark": message["ark"], "msg_type": 3, "msg_id": msg_id, "msg_seq": msg_seq}
        return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload)
    elif message.get("type") == "markdown_keyboard":
        payload = {
            "content": "markdown",
            "msg_type": 2,
            "msg_id": msg_id,
            "keyboard": message.get("keyboard"), "msg_seq": msg_seq}
        return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload)
    elif message.get("type") == "achievement": # 自定义成就消息段
        is_new = await add_achievement(user_id, message.get("achievement_id"))
        if not is_new:
            return {"msg": "User have already got this achievement"}
        file_data = await generate_achievement_image(message.get("achievement_id"))
        payload = {"file_type": 1, "file_data": file_data}
        ret = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
        payload = {"content": "获得了新的成就！", "msg_type": 7, "media": {"file_info": ret["file_info"]}, "msg_id": msg_id,
                   "msg_seq": await get_next_msg_seq(msg_id)}
        return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload, False)
    elif message.get("type") == "markdown":
        payload = {
            "content": "markdown",
            "msg_type": 2,
            "msg_id": msg_id,
            "keyboard": message.get("keyboard"),
            "markdown": message.get("markdown"),
            "msg_seq": msg_seq
        }
        return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload)
    elif message.get("type") == "file":
        if message.get("file_type") == 3:  # silk语音
            if message["data"].startswith("base64://"):
                payload = {"file_type": 3, "file_data": message["data"][9:]}
                silk = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
            elif message["data"].startswith("http://") or message["data"].startswith("https://"):
                payload = {"event_id": msg_id, "file_type": 3, "url": message["data"]}
                silk = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
            elif message["data"].startswith("file:///"):
                file_path = message["data"].lstrip("file:///")
                with open(file_path, "rb") as silk_file:
                    encoded_str = base64.b64encode(silk_file.read()).decode("utf-8")
                payload = {"file_type": 3, "file_data": encoded_str}
                silk = await call_open_api("POST", f"{endpoint}/{union_id}/files", payload)
            else:
                log.warning("传入的silk参数不是正确的base64编码、url或文件路径")
                return await call_open_api("POST", f"{endpoint}/{union_id}/messages",
                                           {"content": "传入的silk参数不是正确的base64编码、url或文件路径",
                                            "msg_type": 0, "msg_id": msg_id, "msg_seq": msg_seq})
            payload = {"msg_type": 7, "media": {"file_info": silk.get("file_info")}, "msg_id": msg_id,
                       "msg_seq": await get_next_msg_seq(msg_id)}
            return await call_open_api("POST", f"{endpoint}/{union_id}/messages", payload)
    else:
        return await call_open_api("POST", f"{endpoint}/{union_id}/messages",{"content": "暂不支持该消息类型", "msg_type": 0, "msg_id": msg_id,"msg_seq": msg_seq},False)


async def delete_im_message(user_id, group_id, message_id):
    endpoint = "/v2/groups" if group_id else "/v2/users"
    id = group_id if group_id else user_id
    union_id = id if TRANSPARENT_OPENID else await get_union_id_by_digit_id(id)
    if str(union_id).isdigit():
        endpoint = "/channels"
    return await call_open_api("DELETE", f"{endpoint}/{union_id}/messages/{message_id}?hidetip=true", None)
