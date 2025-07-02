import sys
import json
import time
import uvicorn
import asyncio
from typing import Optional
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, WebSocket
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from openapi.database import init_db, get_usage_count, flush_usage_to_db, get_union_id_by_digit_id
from openapi.encrypt import verifier
from openapi.inner_cmd import parse_floodgate_cmd
from openapi.parse_open_event import parse_open_message_event, convert_cq_to_openapi_message, parse_group_add
from openapi.token_manage import token_manager
from openapi.network import post_im_message, delete_im_message, post_guild_image, post_floodgate_message
from openapi.tool import check_config, get_health, get_maintaining_message, show_welcome, rate_limit
from config import *


# OpenAPI请求体
class WebhookPayload(BaseModel):
    id: Optional[str] = None
    op: int
    d: dict
    s: Optional[int] = None
    t: Optional[str] = None


# 全局变量
ACCESS_TOKEN = None
WSS_GATEWAY = None


async def refresh_access_token():
    global ACCESS_TOKEN
    try:
        ACCESS_TOKEN = await token_manager.get_access_token()
        log.debug(f"Token刷新成功:{ACCESS_TOKEN}")
    except Exception as e:
        log.error(f"Token刷新失败:{e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await refresh_access_token()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(flush_usage_to_db, trigger=IntervalTrigger(minutes=10))
    scheduler.add_job(refresh_access_token, trigger=IntervalTrigger(seconds=30))
    scheduler.start()
    end_time = time.time()
    log.success(f"Floodgate已启动，耗时: {end_time - start_time:.2f} 秒")
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)
connected_clients = set()
connected_clients_lock = asyncio.Lock()


# 主路由接口
@app.post(WEBHOOK_ENDPOINT)
async def openapi_webhook(request: Request):
    payload = await request.json()
    log.debug(f"收到 OpenAPI 请求: {payload}")
    log.debug(f"请求头: {request.headers}")
    op = payload.get("op")
    d = payload.get("d")
    if op == 13:
        try:
            return await verifier.verify_plain_token(payload)
        except Exception as e:
            log.error(f"发送 WebSocket 消息失败: {e}")
            raise HTTPException(status_code=500, detail="Invalid signature or processing failed")
    elif op == 0:
        if not await verifier.verify_signature(request):
            log.warning(f"事件签名校验失败！")
            raise HTTPException(status_code=401, detail="Invalid Signature")
        t = payload.get("t")
        if t == "GROUP_ADD_ROBOT":
            ob_data = await parse_group_add(d)
        elif t in ["GROUP_AT_MESSAGE_CREATE", "C2C_MESSAGE_CREATE","AT_MESSAGE_CREATE"]:
            if RATE_LIMIT:
                is_rate_limit = await rate_limit(d)
                if is_rate_limit:
                    return {"status": "rate_limit", "op": op}
            global CURRENT_MSG_ID
            await parse_floodgate_cmd(start_time,connected_clients,d)
            ob_data = await parse_open_message_event(CURRENT_MSG_ID, d)
            if not ob_data:
                log.info("平台推送事件消息已去重")
                return {"status": "duplicate", "op": op}
            CURRENT_MSG_ID = ob_data.get("message_id")
        else:
            log.success(f"暂不支持的事件类型：{t}")
            return {"status": "unsupported", "op": op}
        if not connected_clients:  # 判断是否没有已连接的客户端
            await post_floodgate_message(await get_maintaining_message(), d)
            log.warning(f"没有已连接的客户端，当前处于维护模式！")
            return {"status": "maintaining", "op": op}
        async with connected_clients_lock:
            for client in connected_clients:
                try:
                    data = await client.send_json(ob_data)
                    log.debug(f"[WebSocket] 发送 WebSocket 消息成功: {data}")
                except Exception as e:
                    log.error(f"发送 WebSocket 消息失败: {e}")
    return {"status": "ignored", "op": op}


@app.websocket(WS_ENDPOINT)
async def websocket_endpoint(websocket: WebSocket):
    if OB_ACCESS_TOKEN:
        await verifier.verify_onebot_access_token(websocket)
    await websocket.accept()
    async with connected_clients_lock:
        connected_clients.add(websocket)
        log.success(f"新 OneBotv11/DeluxeBOT 客户端接入，当前连接数: {len(connected_clients)}")
        # 这里之后做连接升级
    # 发送 lifecycle.connect 事件
    try:
        await websocket.send_json({"time": int(time.time()), "self_id": str(BOT_APPID), "post_type": "meta_event",
                                   "meta_event_type": "lifecycle", "sub_type": "connect"})
        log.success("已发送握手包")
    except Exception as e:
        log.error(f"发送握手包失败: {e}")
        return

    async def heartbeat():
        while True:
            try:
                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(10)
            except Exception as exc:
                log.warning(f"心跳失败，断开连接: {exc}")
                break

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        while True:
            raw_data = await websocket.receive_text()
            log.debug(f"[WebSocket] 收到客户端消息: {raw_data}")
            try:
                message = json.loads(raw_data)
                if message.get("action") == "send_msg":
                    params = message["params"]
                    msg_list = params.get("message", ["", "", {"type": "text", "data": {"text": "未知异常"}}])
                    if msg_list[0].get("type") == "at" and REMOVE_AT:
                        msg_list = msg_list[2:]
                    ret = await post_im_message(params.get("user_id"), params.get("group_id"),
                                                convert_cq_to_openapi_message(msg_list))
                    await websocket.send_json(
                        {"status": "ok", "retcode": 0, "data": {"message_id": ret.get("id")}, "echo": message["echo"]})
                elif message.get("action") == "delete_msg":
                    message_id = message["params"].get("message_id")
                    if message_id:
                        await delete_im_message(message["params"].get("user_id"), message["params"].get("group_id"),
                                                message_id)
                        await websocket.send_json({"status": "ok", "retcode": 0, "data": {}, "echo": message["echo"]})
                else:
                    await websocket.send_json({"status": "failed", "retcode": 10001, "msg": "Unsupported action"})
            except Exception as e:
                log.error(f"[WebSocket] 处理消息出错: {e}")
                #log.error(f"[Ob11 Request] : {json.loads(raw_data)}")
                await websocket.send_json(
                    {"status": "failed", "retcode": 10002, "msg": f"Error parsing or processing request: {e}"})
    except Exception as e:
        log.warning(f"[WebSocket] 断开连接：{e}")
    finally:
        heartbeat_task.cancel()
        async with connected_clients_lock:
            connected_clients.discard(websocket)
            log.info(f"[WebSocket] 客户端已移除，当前连接数: {len(connected_clients)}")


# 频道图片上传接口
@app.post("/upload_image")
async def upload_image(request: Request):
    data = await request.json()
    return await post_guild_image(data)


class UserStatsRequest(BaseModel):
    id: int


@app.post("/user_stats")
async def user_stats(request: UserStatsRequest):
    usage_count = await get_usage_count(request.id)
    return {"usage_count": usage_count}


@app.get(f"{WEBHOOK_ENDPOINT}/health")
async def health_check():
    return await get_health(start_time,connected_clients)


@app.get("/avatar")
async def avatar(id: int):
    openid = await get_union_id_by_digit_id(id)
    if not openid:
        return {"error": "User not found"}
    return {
        "url": f"https://q.qlogo.cn/qqapp/{BOT_APPID}/{openid}/640"
    }

start_time = time.time()
CURRENT_MSG_ID = 0
if __name__ == "__main__":
    log.remove()
    log.add(sys.stdout, level=LOG_LEVEL, format=LOG_FORMAT)
    import ctypes
    ctypes.windll.kernel32.SetConsoleTitleW(f"Floodgate {VERSION}" if not CUSTOM_TITLE else CUSTOM_TITLE)
    asyncio.run(check_config())
    asyncio.run(show_welcome())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
