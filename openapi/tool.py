import time

from config import log, VERSION, SEQ_CACHE_SIZE, WS_ENDPOINT, WEBHOOK_ENDPOINT, TRANSPARENT_OPENID, SANDBOX_MODE, \
    MAINTAINING_MESSAGE, BOT_NAME, ADMIN_LIST, PORT
from openapi.database import POOL_SIZE, pool, get_pending_counts, get_or_create_digit_id, get_used_user_today, \
    get_usage_today
from openapi.parse_open_event import get_global_message_id

from openapi.token_manage import token_manager


async def check_config():
    from config import BOT_SECRET, BOT_APPID, SANDBOX_CHANNEL_ID
    errors = []
    warnings = []
    if not isinstance(BOT_SECRET, str) or len(BOT_SECRET.strip()) == 0:
        errors.append("BOT_SECRET 未填写")
    if not isinstance(BOT_APPID, int) or BOT_APPID <= 0:
        errors.append("BOT_APPID 必须为正整数")
    if not isinstance(SANDBOX_CHANNEL_ID, int):
        errors.append("SANDBOX_CHANNEL_ID 必须为整数")
    if SANDBOX_CHANNEL_ID == 0:
        warnings.append(
            "SANDBOX_CHANNEL_ID 未填，使用 /upload_image 接口时需要在请求体里提供 channel_id，或填写配置中的 SANDBOX_CHANNEL_ID")
    if errors:
        for error in errors:
            log.error(f"[配置错误] {error}")
        log.error(f"[配置错误] 请在config.py中填写正确信息后重试！")
        exit(1)
    log.success("已通过基础配置检查")
    return True

async def show_welcome():
    log.success("Floodgate Endpoints：")
    base_url = f"http://127.0.0.1:{PORT}"
    log.success(f"{base_url}{WEBHOOK_ENDPOINT}")
    log.success(f"{base_url}{WS_ENDPOINT}")
    log.success(f"{base_url}/health")
    log.success(f"{base_url}/avatar")
    log.success(f"{base_url}/user_stats")
    log.success(f"{base_url}/upload_image")
    log.success(f"{base_url}/docs")
    log.success("Repo: https://github.com/KelsAstell/Floodgate")




async def get_health(start_time, connected_clients):
    from openapi.network import msg_seq_cache
    now = time.time()
    uptime_sec = int(now - start_time)
    days, remainder = divmod(uptime_sec, 86400)  # 一天的秒数
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    try:
        token_remain = await token_manager.remaining_seconds()
    except Exception as e:
        log.warning(f"Token 剩余时间计算失败: {e}")
        token_remain = None

    return {
        "status": "ok",
        "env": 'sandbox' if SANDBOX_MODE else 'production',
        "version": VERSION,  # 版本号
        "repo": "https://github.com/KelsAstell/Floodgate",
        "uptime": f"{hours}h {minutes}m {seconds}s",  # 运行时间
        "clients": len(connected_clients),  # 当前ws客户端数
        "access_token": {  # access_token 状态
            "valid": await token_manager.get_access_token(only_get_token=True) is not None,
            "remain_seconds": token_remain
        },
        "database": {  # 数据库状态
            "pool_size": POOL_SIZE,
            "queue": pool._queue.qsize() if pool._queue else 0
        },
        "cache": {
            "message": {  # 消息缓存状态
                "seq_cache_size": len(msg_seq_cache),
                "seq_cache_size_max": SEQ_CACHE_SIZE,
            },
            "usage": {
                "flush_size": await get_pending_counts()
            }
        },
        "endpoints": {  # 接口地址
            "websocket": WS_ENDPOINT,
            "webhook": WEBHOOK_ENDPOINT
        },
        "transparent": TRANSPARENT_OPENID,
        "dau":await get_used_user_today(),
        "dai":await get_usage_today(),
        "current_msgid": await get_global_message_id()
    }


TEMP_MAINTAINING_MESSAGE = None


async def get_maintaining_message():
    global TEMP_MAINTAINING_MESSAGE
    if TEMP_MAINTAINING_MESSAGE:
        return TEMP_MAINTAINING_MESSAGE
    return MAINTAINING_MESSAGE if MAINTAINING_MESSAGE else f"{BOT_NAME}暂时没有理你，可能是正在维护...再等等吧"


async def set_maintaining_message(message):
    global TEMP_MAINTAINING_MESSAGE
    TEMP_MAINTAINING_MESSAGE = message

async def is_user_admin(d):
    user_id = d.get("author", {}).get("union_openid") if TRANSPARENT_OPENID else await get_or_create_digit_id(d.get("author", {}).get("union_openid"))
    return user_id in ADMIN_LIST