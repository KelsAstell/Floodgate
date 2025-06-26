import base64

import aiohttp
import asyncio
from cachetools import TTLCache
from fastapi import HTTPException

from config import QQ_API_BASE,log
from openapi.database import get_union_id_by_digit_id
from openapi.parse_open_event import message_id_to_open_id
from openapi.token_manage import token_manager

msg_seq_cache = TTLCache(maxsize=100, ttl=300)
# 异步锁，防止并发问题
cache_lock = asyncio.Lock()

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


async def call_open_api(method: str, endpoint: str, payload: dict = None):
    access_token = await token_manager.get_access_token(only_get_token=True)
    if not access_token:
        raise ValueError("无法获取 ACCESS_TOKEN，请尝试重启Floodgate")

    url = QQ_API_BASE + endpoint
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"QQBot {access_token}"
    }

    async with aiohttp.ClientSession() as session:
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
                    log.debug(f"请求成功: {method} {url}, 响应: {data}")
                    return data
                else:
                    error_text = await response.text()
                    log.error(f"请求失败: {method} {url}, 状态码: {response.status}, 错误信息: {error_text}")
                    raise HTTPException(status_code=response.status, detail=error_text)
        except aiohttp.ClientError as e:
            log.error(f"网络请求异常: {e}")
            raise HTTPException(status_code=503, detail=f"请求OpenAPI时出现异常: {e}")


async def post_im_message(user_digit_id, group_digit_id, message):
    msg_id = await message_id_to_open_id(user_digit_id, group_digit_id)
    msg_seq = await get_next_msg_seq(msg_id)
    endpoint = "/v2/groups" if group_digit_id else "/v2/users"
    digit_id = group_digit_id if group_digit_id else user_digit_id
    if message.get("type") == "text":
        payload = {"content": message["text"], "msg_type": 0, "msg_id": msg_id, "msg_seq":msg_seq}
        return await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(digit_id)}/messages", payload)
    elif message.get("type") == "rich_text":
        segments = message["segments"]
        image_info_list = []
        text = ""
        for segment in segments:
            if segment["type"] == "text":
                text += segment["text"]
            elif segment["type"] == "image":
                if segment["url"].startswith("base64://"):
                    payload = {"file_type":1,"file_data":segment["url"][9:]}
                    ret = await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("http://") or segment["url"].startswith("https://"):
                    payload = {"event_id":msg_id,"file_type":1,"url":segment["url"]}
                    ret = await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("file:///"):
                    file_path = segment["url"].lstrip("file:///")
                    with open(file_path, "rb") as image_file:
                        encoded_str = base64.b64encode(image_file.read()).decode("utf-8")
                        payload = {"file_type":1,"file_data":encoded_str}
                        ret = await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/files", payload)
                        image_info_list.append(ret["file_info"])
        if len(image_info_list) > 1:
            for image in image_info_list[:-1]:
                payload = {"msg_type":7,"media":{"file_info":image},"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
                await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages", payload)
        if not len(image_info_list):
            payload = {"content":text, "msg_type":0,"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
        else:
            payload = {"content":text, "msg_type":7,"media":{"file_info":image_info_list[-1]},"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
        await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages", payload)
    elif message.get("type") == "ark":
        payload = {"ark": message["ark"], "msg_type": 3, "msg_id": msg_id, "msg_seq":msg_seq}
        return await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages", payload)
    elif message.get("type") == "markdown_keyboard":
        payload = {
            "content":"markdown",
            "msg_type":2,
            "msg_id":msg_id,
            "keyboard":message.get("keyboard"),"msg_seq":msg_seq}
        return await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages", payload)
    elif message.get("type") == "markdown":
        payload = {
            "content":"markdown",
            "msg_type":2,
            "msg_id":msg_id,
            "keyboard":message.get("keyboard"),
            "markdown":message.get("markdown"),
            "msg_seq":msg_seq
        }
        return await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages", payload)
    elif message.get("type") == "file":
        if message.get("file_type") == 3: # silk语音
            if message["data"].startswith("base64://"):
                payload = {"file_type":3,"file_data":message["data"][9:]}
                silk = await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/files", payload)
                payload = {"msg_type":7,"media":{"file_info":silk},"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
                await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages", payload)
            else:
                log.warning("传入的silk不是合法的base64编码")
    else:
        return await call_open_api("POST", f"{endpoint}/{await get_union_id_by_digit_id(digit_id)}/messages", {"content": "暂不支持该消息类型", "msg_type": 0, "msg_id": msg_id, "msg_seq":msg_seq})



# 发送群消息
async def post_group_message(user_digit_id, group_digit_id, message):
    msg_id = await message_id_to_open_id(user_digit_id, group_digit_id)
    msg_seq = await get_next_msg_seq(msg_id)
    if message.get("type") == "text":
        payload = {"content": message["text"], "msg_type": 0, "msg_id": msg_id, "msg_seq":msg_seq}
        return await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/messages", payload)
    elif message.get("type") == "rich_text":
        segments = message["segments"]
        image_info_list = []
        text = ""
        for segment in segments:
            if segment["type"] == "text":
                text += segment["text"]
            elif segment["type"] == "image":
                if segment["url"].startswith("base64://"):
                    payload = {"file_type":1,"file_data":segment["url"][9:]}
                    ret = await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("http://") or segment["url"].startswith("https://"):
                    payload = {"event_id":msg_id,"file_type":1,"url":segment["url"]}
                    ret = await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("file:///"):
                    file_path = segment["url"].lstrip("file:///")
                    with open(file_path, "rb") as image_file:
                        encoded_str = base64.b64encode(image_file.read()).decode("utf-8")
                        payload = {"file_type":1,"file_data":encoded_str}
                        ret = await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/files", payload)
                        image_info_list.append(ret["file_info"])
        if len(image_info_list) > 1:
            for image in image_info_list[:-1]:
                payload = {"msg_type":7,"media":{"file_info":image},"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
                await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/messages", payload)
        if not len(image_info_list):
            payload = {"content":text, "msg_type":0,"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
        else:
            payload = {"content":text, "msg_type":7,"media":{"file_info":image_info_list[-1]},"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
        await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/messages", payload)
    elif message.get("type") == "ark":
        payload = {"ark": message["ark"], "msg_type": 3, "msg_id": msg_id, "msg_seq":msg_seq}
        return await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/messages", payload)
    elif message.get("type") == "markdown_keyboard":
        payload = {
            "content":"markdown",
            "msg_type":2,
            "msg_id":msg_id,
            "keyboard":message.get("keyboard"),"msg_seq":msg_seq}
        return await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/messages", payload)
    elif message.get("type") == "markdown":
        payload = {
            "content":"markdown",
            "msg_type":2,
            "msg_id":msg_id,
            "keyboard":message.get("keyboard"),
            "markdown":message.get("markdown"),
            "msg_seq":msg_seq
        }
        return await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/messages", payload)
    else:
        return await call_open_api("POST", f"/v2/groups/{await get_union_id_by_digit_id(group_digit_id)}/messages", {"content": "暂不支持该消息类型", "msg_type": 0, "msg_id": msg_id, "msg_seq":msg_seq})

# 发送私聊消息
async def post_direct_message(user_digit_id, group_digit_id, message):
    msg_id = await message_id_to_open_id(user_digit_id, group_digit_id)
    msg_seq = await get_next_msg_seq(msg_id)
    if message.get("type") == "text":
        payload = {"content": message["text"], "msg_type": 0, "msg_id": msg_id, "msg_seq":msg_seq}
        return await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/messages", payload)
    elif message.get("type") == "rich_text":
        segments = message["segments"]
        image_info_list = []
        text = ""
        for segment in segments:
            if segment["type"] == "text":
                text += segment["text"]
            elif segment["type"] == "image":
                if segment["url"].startswith("base64://"):
                    payload = {"file_type":1,"file_data":segment["url"][9:]}
                    ret = await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("http://") or segment["url"].startswith("https://"):
                    payload = {"event_id":msg_id,"file_type":1,"url":segment["url"]}
                    ret = await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/files", payload)
                    image_info_list.append(ret["file_info"])
                elif segment["url"].startswith("file:///"):
                    file_path = segment["url"].lstrip("file:///")
                    with open(file_path, "rb") as image_file:
                        encoded_str = base64.b64encode(image_file.read()).decode("utf-8")
                        payload = {"file_type":1,"file_data":encoded_str}
                        ret = await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/files", payload)
                        image_info_list.append(ret["file_info"])
        if len(image_info_list) > 1:
            for image in image_info_list[:-1]:
                payload = {"msg_type":7,"media":{"file_info":image},"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
                await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/messages", payload)
        if not len(image_info_list):
            payload = {"content":text, "msg_type":0,"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
        else:
            payload = {"content":text, "msg_type":7,"media":{"file_info":image_info_list[-1]},"msg_id":msg_id,"msg_seq":await get_next_msg_seq(msg_id)}
        await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/messages", payload)
    elif message.get("type") == "ark": # 这玩意支持私聊吗？我不知道，让我逝一下..哦好像确实可以，那留着吧
        payload = {"ark": message["ark"], "msg_type": 3, "msg_id": msg_id, "msg_seq":msg_seq}
        return await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/messages", payload)
    elif message.get("type") == "markdown_keyboard":
        payload = {
            "content":"markdown",
            "msg_type":2,
            "msg_id":msg_id,
            "keyboard":message.get("keyboard"),"msg_seq":msg_seq}
        return await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/messages", payload)
    else:
        return await call_open_api("POST", f"/v2/users/{await get_union_id_by_digit_id(user_digit_id)}/messages", {"content": "暂不支持该消息类型", "msg_type": 0, "msg_id": msg_id, "msg_seq":msg_seq})
