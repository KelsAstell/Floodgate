import sys
import json
import time
import uvicorn
import asyncio
import uuid
from typing import Optional, Any, List

from cachetools import TTLCache

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, WebSocket, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from openapi.database import init_db, get_usage_count, flush_usage_to_db, get_union_id_by_digit_id, get_or_create_digit_id, reset_usage_today, close_db_pool, add_achievement, get_achievement_list, get_achievement_stat
from openapi.encrypt import verifier
from openapi.inner_cmd import parse_floodgate_cmd
from openapi.oauth import oauth_manager
from openapi.parse_open_event import parse_open_message_event, convert_cq_to_openapi_message, parse_group_add
from openapi.token_manage import token_manager
from openapi.network import post_im_message, delete_im_message, post_guild_image, post_floodgate_message, close_http_session
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

# OAuth 命令响应消息队列（按 user_id 匹配）
# 结构: {user_id: asyncio.Queue}
oauth_response_queues = {}
oauth_response_queues_lock = asyncio.Lock()

# OAuth 消息内容缓存（按 message_id 存储完整 OneBot 事件）
# 结构: {message_id: {"user_id": <user_id>, "event": <onebot_event_dict>}}
oauth_message_cache = TTLCache(maxsize=5000, ttl=120)


async def process_oauth_message(message: dict) -> dict:
    """
    处理 OAuth 响应消息，将消息段中的本地文件路径转换为 base64 编码
    支持的消息类型：record (语音)、image (图片)、video (视频) 等
    
    Args:
        message: 原始消息字典
        
    Returns:
        处理后的消息字典
    """
    import base64
    import copy
    
    # 深拷贝消息，避免修改原消息
    processed_message = copy.deepcopy(message)
    
    # 获取消息列表
    params = processed_message.get("params", {})
    message_list = params.get("message", [])
    
    # 需要处理文件路径的消息类型及其文件字段名
    file_types = {
        "record": "file",   # 语音消息
        "image": "file",    # 图片消息
        "video": "file",    # 视频消息
        "face": "file",     # 表情消息（如果有文件）
    }
    
    # 遍历消息段，处理包含文件的类型
    for i, seg in enumerate(message_list):
        seg_type = seg.get("type")
        if seg_type in file_types:
            data = seg.get("data", {})
            file_field = file_types[seg_type]
            file_path = data.get(file_field, "")
            
            # 检查是否是本地文件路径
            if file_path.startswith("file:///"):
                try:
                    # 去除 file:/// 前缀
                    local_path = file_path[8:]  # file:/// 有 8 个字符
                    
                    # 读取文件并转换为 base64
                    with open(local_path, "rb") as f:
                        file_content = f.read()
                        base64_data = base64.b64encode(file_content).decode("utf-8")
                    
                    # 替换为 base64 格式
                    message_list[i]["data"][file_field] = f"base64://{base64_data}"
                    log.info(f"[OAuth Message] 已将 {seg_type} 类型本地文件转换为 base64，原路径: {file_path}")
                    
                except Exception as e:
                    log.error(f"[OAuth Message] 转换 {seg_type} 文件失败: {e}, 路径: {file_path}")
                    # 转换失败时保留原路径
            
            # 如果已经是 base64 或 URL，保持不变
            elif file_path.startswith("base64://") or file_path.startswith("http://") or file_path.startswith("https://"):
                log.debug(f"[OAuth Message] {seg_type} 类型已是 base64 或 URL 格式，无需转换")
    
    return processed_message


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
    scheduler.add_job(reset_usage_today, trigger=CronTrigger(hour=0, minute=0))
    scheduler.add_job(refresh_access_token, trigger=IntervalTrigger(seconds=30))
    scheduler.start()
    end_time = time.time()
    log.success(f"Floodgate已启动，耗时: {end_time - start_time:.2f} 秒")
    yield
    scheduler.shutdown()
    await close_http_session()  # 关闭全局 HTTP Session
    await close_db_pool()  # 关闭数据库连接池


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
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
            log.success(f"收到 OpenAPI 验证请求")
            return await verifier.verify_plain_token(d)
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
            await parse_floodgate_cmd(start_time,connected_clients,payload,request.headers)
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
        
        async def send_to_client(client, data):
            try:
                await client.send_json(data)
                log.debug(f"[WebSocket] 发送 WebSocket 消息成功")
            except Exception as e:
                log.error(f"发送 WebSocket 消息失败: {e}")
        
        async with connected_clients_lock:
            await asyncio.gather(*[send_to_client(c, ob_data) for c in connected_clients])
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
                echo = message.get("echo")
                
                if message.get("action") == "send_msg":
                    params = message["params"]
                    user_id = params.get("user_id")
                    group_id = params.get("group_id")
                    
                    # 检查是否是 OAuth 请求的响应（group_id = 1）
                    if group_id == 1:
                        log.info(f"[OAuth Response] 收到 OAuth 响应，user_id={user_id}")
                        log.info(f"[OAuth Response] 响应内容: {json.dumps(message, ensure_ascii=False)}")
                        
                        # 处理消息中的 record 类型（silk 语音）
                        processed_message = await process_oauth_message(message)
                        
                        # 检查消息中是否包含成就段，若用户已获得则丢弃（避免重复推送）
                        msg_segments = processed_message.get("params", {}).get("message", [])
                        should_discard = False
                        for seg in msg_segments:
                            if seg.get("type") == "achievement":
                                ach_id = seg.get("data", {}).get("id")
                                if ach_id is not None:
                                    is_new = await add_achievement(str(user_id), ach_id)
                                    if not is_new:
                                        log.info(f"[OAuth Response] 用户已获得成就 {ach_id}，丢弃重复成就消息，user_id={user_id}")
                                        should_discard = True
                                        break
                        
                        if not should_discard:
                            # 为该条消息生成唯一 message_id，并写入缓存
                            message_id = str(uuid.uuid4())
                            oauth_message_cache[message_id] = {
                                "user_id": user_id,
                                "event": processed_message,
                            }
                            
                            async with oauth_response_queues_lock:
                                if user_id in oauth_response_queues:
                                    # 将 message_id 放入该用户的队列
                                    queue_size = oauth_response_queues[user_id].qsize()
                                    await oauth_response_queues[user_id].put({
                                        "type": "message_ref",
                                        "message_id": message_id,
                                    })
                                    #log.success(f"[OAuth Response] 响应消息已入队，user_id={user_id}, 队列大小={queue_size + 1}")
                                else:
                                    log.warning(f"[OAuth Response] 用户未建立 SSE 连接，消息被丢弃，user_id={user_id}")
                        
                        # OAuth 响应不发送到 OpenAPI，但要回复 WebSocket 客户端
                        ws_response = {"status": "ok", "retcode": 0, "data": {"message_id": "oauth_handled"}, "echo": echo}
                        await websocket.send_json(ws_response)
                        log.debug(f"[OAuth Response] 已回复 WebSocket 客户端: {ws_response}")
                        continue
                    
                    msg_list = params.get("message", ["", "", {"type": "text", "data": {"text": "未知异常"}}])
                    if msg_list[0].get("type") == "at" and REMOVE_AT:
                        msg_list = msg_list[2:]
                    ret = await post_im_message(user_id, group_id,
                                                convert_cq_to_openapi_message(msg_list))
                    await websocket.send_json(
                        {"status": "ok", "retcode": 0, "data": {"message_id": ret.get("id")}, "echo": echo})
                elif message.get("action") == "delete_msg":
                    message_id = message["params"].get("message_id")
                    if message_id:
                        await delete_im_message(message["params"].get("user_id"), message["params"].get("group_id"),
                                                message_id)
                        await websocket.send_json({"status": "ok", "retcode": 0, "data": {}, "echo": echo})
                else:
                    await websocket.send_json({"status": "failed", "retcode": 10001, "msg": "Unsupported action"})
            except Exception as e:
                log.error(f"[WebSocket] 处理消息出错: {e}")
                log.error(f"[Ob11 Request] : {json.loads(raw_data)}")
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


# OAuth请求体模型
class OAuthLoginRequest(BaseModel):
    token: str


class OAuthCommandRequest(BaseModel):
    action: str
    params: dict = {}
    echo: Optional[Any] = None


@app.post("/user_stats")
async def user_stats(request: UserStatsRequest):
    usage_count = await get_usage_count(request.id)
    return {"usage_count": usage_count}


@app.get(f"{WEBHOOK_ENDPOINT}/health")
async def health_check():
    return await get_health(start_time,connected_clients)


@app.get(f"{WEBHOOK_ENDPOINT}/achievements")
async def achievements(uid: int):
    if not ACHIEVEMENT_PERSIST:
        raise HTTPException(status_code=503, detail="Achievement system is disabled")
    achievement_ids = await get_achievement_list(str(uid))
    return {"uid": uid, "achievements": achievement_ids}


@app.get(f"{WEBHOOK_ENDPOINT}/achievement_stat")
async def achievement_stat():
    if not ACHIEVEMENT_PERSIST:
        raise HTTPException(status_code=503, detail="Achievement system is disabled")
    return await get_achievement_stat()


@app.get("/avatar")
async def avatar(id: int):
    openid = await get_union_id_by_digit_id(id)
    if not openid:
        return {"error": "User not found"}
    return {
        "url": f"https://q.qlogo.cn/qqapp/{BOT_APPID}/{openid}/640"
    }


# OAuth登录接口
@app.post(f"{WEBHOOK_ENDPOINT}/oauth_login")
async def oauth_login(request: OAuthLoginRequest):
    """使用登录令牌换取JWT"""
    union_openid = oauth_manager.verify_login_token(request.token)
    if not union_openid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    jwt_token, expires_in = oauth_manager.create_jwt(union_openid)
    
    # 获取数字userid
    if not TRANSPARENT_OPENID:
        user_id = await get_or_create_digit_id(union_openid)
    else:
        user_id = union_openid
    
    return {
        "jwt": jwt_token,
        "expires_in": expires_in,
        "token_type": "Bearer",
        "userid": user_id
    }


# OAuth命令代理接口
@app.post(f"{WEBHOOK_ENDPOINT}/oauth_command")
async def oauth_command(request: OAuthCommandRequest, authorization: Optional[str] = Header(None), req: Request = None):
    """使用JWT认证，将命令转发给OneBot客户端，立即返回。响应通过SSE接口获取"""
    # 打印请求信息
    client_ip = req.client.host if req and req.client else "unknown"
    log.info(f"[OAuth Command] 收到命令请求，客户端IP: {client_ip}")
    log.info(f"[OAuth Command] 请求参数: action={request.action}, params={json.dumps(request.params, ensure_ascii=False)}")
    
    # 验证JWT
    if not authorization or not authorization.startswith("Bearer "):
        log.warning(f"[OAuth Command] 认证失败: 缺少或无效的 Authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    jwt_token = authorization[7:]  # 移除 "Bearer " 前缀
    log.debug(f"[OAuth Command] JWT Token: {jwt_token[:20]}...")
    
    union_openid = oauth_manager.verify_jwt(jwt_token)
    if not union_openid:
        log.warning(f"[OAuth Command] JWT 验证失败")
        raise HTTPException(status_code=401, detail="Invalid or expired JWT token")
    
    log.info(f"[OAuth Command] JWT 验证成功，union_openid={union_openid}")
    
    # 检查是否有已连接的客户端
    if not connected_clients:
        log.error(f"[OAuth Command] 没有已连接的 OneBot 客户端")
        raise HTTPException(status_code=503, detail="No OneBot client connected")
    
    log.info(f"[OAuth Command] OneBot 客户端连接数: {len(connected_clients)}")
    
    # 获取用户的数字ID
    if TRANSPARENT_OPENID:
        user_id = union_openid
    else:
        user_id = await get_or_create_digit_id(union_openid)
    
    log.info(f"[OAuth Command] 用户ID映射完成，user_id={user_id}")
    
    # 构造 OneBot 消息事件
    raw_message = request.params.get("message", "")
    if isinstance(raw_message, list):
        # 提取纯文本
        raw_message = "".join(
            seg.get("data", {}).get("text", "") 
            for seg in raw_message 
            if seg.get("type") == "text"
        )
    
    log.info(f"[OAuth Command] 原始消息文本: {raw_message}")
    
    # 检查是否为内部命令（以 ~ 开头）
    if raw_message.strip().startswith("~"):
        log.info(f"[OAuth Command] 检测到内部命令: {raw_message}")
        
        # 处理内部命令并直接通过 SSE 推送响应
        try:
            cmd = raw_message.strip()[1:]  # 移除 ~ 前缀
            response_text = None
            
            # health 命令
            if cmd.startswith("health"):
                from openapi.tool import get_health
                data = await get_health(start_time, connected_clients)
                cache = data.get('cache')
                response_text = (
                    f"Floodgate：{'✅已连接' if data['clients'] > 0 else '❌未连接'}({data['clients']}个实例)\n"
                    f"版本号：{data['version']}-{data['env']}\n"
                    f"运行时长：{data['uptime']}\n"
                    f"Token有效期：{data['access_token']['remain_seconds']}秒\n"
                    f"消息补发：成功({data['send_failed'].get('success', 0)}) | 失败({data['send_failed'].get('failed', 0)})\n"
                    f"内存缓存利用率：{100 * cache['message']['seq_cache_size'] / cache['message']['seq_cache_size_max']:.2f}%\n"
                    f"待提交的统计：{cache['usage']['flush_size']}"
                )
            
            # login 命令
            # elif cmd.startswith("login"):
            #     token = oauth_manager.generate_login_token(union_openid)
            #     ttl_minutes = OAUTH_LOGIN_TOKEN_TTL // 60
            #     response_text = f"您的登录令牌为：{token}\n有效期{ttl_minutes}分钟，请勿泄露。"
            
            # 成就命令
            elif cmd.startswith("成就"):
                from openapi.database import get_achievement_list
                from openapi.draw_ach import generate_achievement_page_image
                import re
                match = re.search(r"成就\s*(\d*)", cmd)
                page = 1
                if match and match.group(1):
                    try:
                        page = int(match.group(1))
                    except ValueError:
                        page = 1
                
                user_achievements = await get_achievement_list(str(user_id)) if ACHIEVEMENT_PERSIST else []
                base64_img = await generate_achievement_page_image(user_achievements, page=page)
                
                # 对于图片响应，推送特殊格式
                # 构造完整事件并通过 message_id + oauth_content 拉取
                event = {
                    "action": "send_msg",
                    "params": {
                        "message": [
                            {"type": "text", "data": {"text": "命令：~成就 x 可查看指定的页\n例如：~成就 2"}},
                            {"type": "image", "data": {"file": f"base64://{base64_img}"}}
                        ]
                    }
                }
                message_id = str(uuid.uuid4())
                oauth_message_cache[message_id] = {
                    "user_id": user_id,
                    "event": event,
                }
                async with oauth_response_queues_lock:
                    if user_id in oauth_response_queues:
                        await oauth_response_queues[user_id].put({
                            "type": "message_ref",
                            "message_id": message_id,
                        })
                        #log.success(f"[OAuth Command] 内部命令响应已推送到 SSE，user_id={user_id}")
                    else:
                        log.warning(f"[OAuth Command] 用户未建立 SSE 连接，响应消息丢弃，user_id={user_id}")
                
                return {
                    "status": "ok",
                    "retcode": 0,
                    "msg": "Internal command processed and response sent via SSE.",
                    "echo": request.echo
                }
            
            # 其他命令暂不支持（需要管理员权限或其他复杂逻辑）
            else:
                response_text = f"OAuth 接口暂不支持命令: ~{cmd}"
            
            # 将文本响应推送到 SSE（统一走 message_id + oauth_content 模式）
            if response_text:
                # 构造文本消息事件
                event = {
                    "action": "send_msg",
                    "params": {
                        "message": [
                            {"type": "text", "data": {"text": response_text}}
                        ]
                    }
                }
                message_id = str(uuid.uuid4())
                oauth_message_cache[message_id] = {
                    "user_id": user_id,
                    "event": event,
                }
                async with oauth_response_queues_lock:
                    if user_id in oauth_response_queues:
                        await oauth_response_queues[user_id].put({
                            "type": "message_ref",
                            "message_id": message_id,
                        })
                        #log.success(f"[OAuth Command] 内部命令响应已推送到 SSE，user_id={user_id}")
                    else:
                        log.warning(f"[OAuth Command] 用户未建立 SSE 连接，响应消息丢弃，user_id={user_id}")
            
            return {
                "status": "ok",
                "retcode": 0,
                "msg": "Internal command processed and response sent via SSE.",
                "echo": request.echo
            }
            
        except Exception as e:
            log.error(f"[OAuth Command] 内部命令处理失败: {e}")
            import traceback
            log.error(f"[OAuth Command] 堆栈跟踪:\n{traceback.format_exc()}")
            
            # 推送错误消息到 SSE
            async with oauth_response_queues_lock:
                if user_id in oauth_response_queues:
                    await oauth_response_queues[user_id].put({
                        "action": "send_msg",
                        "params": {
                            "message": [{"type": "text", "data": {"text": f"内部命令执行失败: {str(e)}"}}]
                        }
                    })
            
            return {
                "status": "error",
                "retcode": -1,
                "msg": f"Internal command failed: {str(e)}",
                "echo": request.echo
            }
    
    # 非内部命令，正常转发给 OneBot 客户端
    ob_event = {
        "time": int(time.time()),
        "self_id": str(BOT_APPID),
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": int(time.time() * 1000) % 2147483647,
        "user_id": user_id,
        "group_id": 1,  # 固定为 1
        "message": request.params.get("message", [{"type": "text", "data": {"text": ""}}]),
        "raw_message": raw_message,
        "font": 0,
        "sender": {
            "user_id": user_id,
            "nickname": "OAuth User",
            "card": "",
            "sex": "unknown",
            "age": 0,
            "role": "member"
        }
    }
    
    log.info(f"[OAuth Command] 构造的 OneBot 事件: {json.dumps(ob_event, ensure_ascii=False)}")
    
    # 检查是否有 SSE 连接
    async with oauth_response_queues_lock:
        has_sse = user_id in oauth_response_queues
    
    if has_sse:
        pass
        #log.success(f"[OAuth Command] 用户已建立 SSE 连接，响应将推送到 SSE，user_id={user_id}")
    else:
        log.warning(f"[OAuth Command] 用户未建立 SSE 连接，响应消息将被丢弃，user_id={user_id}")
    
    # 广播给所有 OneBot 客户端
    async def send_to_client(client, data):
        try:
            await client.send_json(data)
            log.info(f"[OAuth Command] 已发送到 OneBot 客户端")
        except Exception as e:
            log.error(f"[OAuth Command] 发送消息失败: {e}")
    
    async with connected_clients_lock:
        await asyncio.gather(*[send_to_client(c, ob_event) for c in connected_clients])
    
    #log.success(f"[OAuth Command] 命令已广播给 {len(connected_clients)} 个 OneBot 客户端，user_id={user_id}")
    
    # 立即返回成功，响应通过 SSE 接口获取
    response = {"status": "ok", "retcode": 0, "msg": "Command sent", "echo": request.echo}
    log.info(f"[OAuth Command] 返回响应: {response}")
    return response


# OAuth 内容拉取接口
@app.get(f"{WEBHOOK_ENDPOINT}/oauth_content")
async def oauth_content(message_id: str, authorization: Optional[str] = Header(None)):
    """使用JWT认证，根据 message_id 拉取完整 OneBot 事件内容

    - 实现端到端语义：SSE 只传 message_id，真正内容通过该接口单独拉取
    - 成功返回后会删除缓存中的这条 message_id 记录
    """
    # 验证 JWT
    if not authorization or not authorization.startswith("Bearer "):
        log.warning(f"[OAuth Content] 认证失败: 缺少或无效的 Authorization header")
        return {"status": "error", "code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header"}

    jwt_token = authorization[7:]
    log.debug(f"[OAuth Content] JWT Token: {jwt_token[:20]}...")

    union_openid = oauth_manager.verify_jwt(jwt_token)
    if not union_openid:
        log.warning(f"[OAuth Content] JWT 验证失败")
        return {"status": "error", "code": "INVALID_TOKEN", "message": "Invalid or expired JWT token"}

    # 获取数字 user_id（与 oauth_command / oauth_stream 保持一致）
    if TRANSPARENT_OPENID:
        user_id = union_openid
    else:
        user_id = await get_or_create_digit_id(union_openid)

    log.info(f"[OAuth Content] JWT 验证成功，union_openid={union_openid}, user_id={user_id}")

    # 从缓存中读取并删除 message
    data = oauth_message_cache.pop(message_id, None)
    if not data:
        log.warning(f"[OAuth Content] message_id 不存在或已过期: {message_id}")
        return {"status": "error", "code": "MESSAGE_NOT_FOUND", "message": "Message not found or expired"}

    # 权限校验：必须是自己的消息
    if str(data.get("user_id")) != str(user_id):
        log.warning(f"[OAuth Content] message_id 所属用户与当前用户不匹配, message_user_id={data.get('user_id')}, current_user_id={user_id}")
        return {"status": "error", "code": "FORBIDDEN", "message": "Message does not belong to current user"}

    event = data.get("event")
    if event is None:
        log.error(f"[OAuth Content] 缓存记录中缺少 event 字段, message_id={message_id}")
        return {"status": "error", "code": "INVALID_MESSAGE_DATA", "message": "Invalid message data"}

    log.info(f"[OAuth Content] 返回消息内容, message_id={message_id}, user_id={user_id}")
    return {"status": "ok", "code": "OK", "message": "Success", "data": event}


# OAuth SSE 响应流接口
@app.get(f"{WEBHOOK_ENDPOINT}/oauth_stream")
async def oauth_stream(authorization: Optional[str] = Header(None), request: Request = None):
    """使用JWT认证，建立SSE连接接收该用户的所有响应消息"""
    # 打印请求信息
    client_ip = request.client.host if request and request.client else "unknown"
    log.info(f"[OAuth SSE] 收到连接请求，客户端IP: {client_ip}")
    log.debug(f"[OAuth SSE] 请求头: {dict(request.headers) if request else {}}")
    
    # 验证JWT
    if not authorization or not authorization.startswith("Bearer "):
        log.warning(f"[OAuth SSE] 认证失败: 缺少或无效的 Authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    jwt_token = authorization[7:]  # 移除 "Bearer " 前缀
    log.debug(f"[OAuth SSE] JWT Token: {jwt_token[:20]}...")
    
    union_openid = oauth_manager.verify_jwt(jwt_token)
    if not union_openid:
        log.warning(f"[OAuth SSE] JWT 验证失败")
        raise HTTPException(status_code=401, detail="Invalid or expired JWT token")
    
    log.info(f"[OAuth SSE] JWT 验证成功，union_openid={union_openid}")
    
    # 获取用户的数字ID
    if TRANSPARENT_OPENID:
        user_id = union_openid
    else:
        user_id = await get_or_create_digit_id(union_openid)
    
    log.info(f"[OAuth SSE] 用户ID映射完成，user_id={user_id}")
    
    # 为该用户创建消息队列
    message_queue = asyncio.Queue()
    async with oauth_response_queues_lock:
        # 检查是否已有连接
        if user_id in oauth_response_queues:
            log.warning(f"[OAuth SSE] 用户已有活跃连接，将替换旧连接，user_id={user_id}")
        oauth_response_queues[user_id] = message_queue
    
    #log.success(f"[OAuth SSE] 客户端已连接，user_id={user_id}, client_ip={client_ip}")
    
    async def event_generator():
        message_count = 0
        try:
            # 发送连接成功消息
            connect_msg = {'type': 'connected', 'user_id': user_id}
            connect_data = f"data: {json.dumps(connect_msg)}\n\n"
            log.info(f"[OAuth SSE] >>> 发送连接消息: {connect_msg}")
            yield connect_data
            
            # 持续监听消息队列
            while True:
                try:
                    # 等待消息，超时60秒发送心跳
                    log.debug(f"[OAuth SSE] 等待消息... user_id={user_id}")
                    message = await asyncio.wait_for(message_queue.get(), timeout=60.0)
                    message_count += 1
                    
                    # 打印收到的消息
                    log.info(f"[OAuth SSE] <<< 收到第 {message_count} 条消息，user_id={user_id}")
                    log.info(f"[OAuth SSE] 消息内容: {json.dumps(message, ensure_ascii=False)}")
                    
                    # 发送消息
                    message_data = f"data: {json.dumps(message)}\n\n"
                    log.info(f"[OAuth SSE] >>> 推送第 {message_count} 条消息，user_id={user_id}")
                    yield message_data
                    
                except asyncio.TimeoutError:
                    # 发送心跳
                    heartbeat_data = f": heartbeat\n\n"
                    log.debug(f"[OAuth SSE] >>> 发送心跳，user_id={user_id}")
                    yield heartbeat_data
                    
        except asyncio.CancelledError:
            log.info(f"[OAuth SSE] 连接被取消，user_id={user_id}, 已发送 {message_count} 条消息")
        except Exception as e:
            log.error(f"[OAuth SSE] 异常断开，user_id={user_id}, error={e}")
            import traceback
            log.error(f"[OAuth SSE] 堆栈跟踪:\n{traceback.format_exc()}")
        finally:
            # 清理队列
            async with oauth_response_queues_lock:
                if user_id in oauth_response_queues:
                    oauth_response_queues.pop(user_id)
                    log.info(f"[OAuth SSE] 已清理消息队列，user_id={user_id}")
            #log.success(f"[OAuth SSE] 客户端已断开，user_id={user_id}, 总共发送 {message_count} 条消息")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            "X-Content-Type-Options": "nosniff",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked"  # 显式声明分块传输
        }
    )

start_time = time.time()
CURRENT_MSG_ID = 0
if __name__ == "__main__":
    log.remove()
    log.add(sys.stdout, level=LOG_LEVEL, format=LOG_FORMAT)
    log.add("warnings_and_errors.log", level="WARNING", rotation="10 MB", retention="7 days", encoding="utf-8")
    import ctypes
    ctypes.windll.kernel32.SetConsoleTitleW(f"Floodgate {VERSION}" if not CUSTOM_TITLE else CUSTOM_TITLE)
    asyncio.run(check_config())
    asyncio.run(show_welcome())
    # 缩短 oauth_content 的 uvicorn access log（去掉 URL 中的 message_id 参数）
    import logging
    class _ShortenOAuthContentLog(logging.Filter):
        def filter(self, record):
            if record.args and 'oauth_content' in record.getMessage():
                record.args = tuple(
                    arg.split('?')[0] if isinstance(arg, str) and 'oauth_content?' in arg else arg
                    for arg in record.args
                )
            return True
    logging.getLogger("uvicorn.access").addFilter(_ShortenOAuthContentLog())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
