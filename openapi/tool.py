import json
import os
import time
from config import *
from openapi.database import POOL_SIZE, pool, get_pending_counts, get_or_create_digit_id, get_dau_today
from openapi.network import get_send_failed_count, post_floodgate_message
from openapi.parse_open_event import get_global_message_id

from openapi.token_manage import token_manager


async def check_config():
    from config import BOT_SECRET, BOT_APPID, SANDBOX_CHANNEL_ID
    errors = []
    warnings = []
    os.makedirs("logs", exist_ok=True)
    log.add(
        os.path.join("logs", "{time:YYYY-MM-DD}.log"),
        level="WARNING",
        rotation="00:00",            # 每天 00:00 分割
        retention="7 days",          # 保留 7 天
        encoding="utf-8",
        enqueue=True,                # 多线程/多进程安全（推荐开启）
        backtrace=True,              # 错误日志中显示完整堆栈
        diagnose=True                # 显示变量值
    )
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
    log.success(f"{base_url}{WEBHOOK_ENDPOINT}/health")
    log.success(f"{base_url}/avatar")
    log.success(f"{base_url}/user_stats")
    log.success(f"{base_url}/upload_image")
    log.success(f"{base_url}/docs")
    log.success("Repo: https://github.com/KelsAstell/Floodgate")




async def _get_db_queue_size():
    """获取数据库队列/连接状态"""
    from openapi.database import db_manager
    try:
        if db_manager.get_type() == "postgresql":
            # PostgreSQL: 获取连接池中的空闲连接数
            backend = db_manager._backend
            if backend and backend._pool:
                return backend._pool.get_idle_size()
            return 0
        else:
            # SQLite: 单连接模式，返回 0 或 1 表示连接状态
            return 1 if db_manager._backend and db_manager._backend._initialized else 0
    except Exception:
        return 0


async def get_health(start_time, connected_clients):
    from openapi.network import msg_seq_cache
    now = time.time()
    uptime_sec = int(now - start_time)
    if uptime_sec >= 86400:
        days, remainder = divmod(uptime_sec, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
    else:
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
    try:
        token_remain = await token_manager.remaining_seconds()
    except Exception as e:
        log.warning(f"Token 剩余时间计算失败: {e}")
        token_remain = None
    dau_dict = await get_dau_today()
    return {
        "status": "ok",
        "env": 'sandbox' if SANDBOX_MODE else 'production',
        "version": VERSION,  # 版本号
        "repo": "https://github.com/KelsAstell/Floodgate",
        "uptime": uptime_str,  # 运行时间
        "clients": len(connected_clients),  # 当前ws客户端数
        "access_token": {  # access_token 状态
            "valid": await token_manager.get_access_token(only_get_token=True) is not None,
            "remain_seconds": token_remain
        },
        "database": {  # 数据库状态
            "pool_size": POOL_SIZE,
            "queue": await _get_db_queue_size()
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
        "dau":dau_dict.get("dau",0),
        "dai":dau_dict.get("dai",0),
        "current_msgid": await get_global_message_id(),
        "send_failed": await get_send_failed_count()
    }


TEMP_MAINTAINING_MESSAGE = None


async def get_maintaining_message():
    return TEMP_MAINTAINING_MESSAGE or MAINTAINING_MESSAGE


async def set_maintaining_message(message):
    global TEMP_MAINTAINING_MESSAGE
    TEMP_MAINTAINING_MESSAGE = message

async def is_user_admin(d):
    user_id = d.get("author", {}).get("union_openid") if TRANSPARENT_OPENID else await get_or_create_digit_id(d.get("author", {}).get("union_openid"))
    return user_id in ADMIN_LIST

from collections import defaultdict, deque
from datetime import datetime, timedelta, date

user_message_history = defaultdict(deque)
temp_ban_until = {}  # uid -> 解封时间

async def rate_limit(d):
    uid = d.get("author", {}).get("union_openid")
    # 自己人，管理员不限速
    if await is_user_admin(d):
        return False
    now = datetime.now()
    # 检查是否被临时封禁
    if uid in temp_ban_until and now < temp_ban_until[uid]:
        log.warning(f"{uid}({await get_or_create_digit_id(uid)})发送频率过高，临时封禁至 {temp_ban_until[uid]}")
        await post_floodgate_message(f"🧊你发送得太快啦，请 {int((temp_ban_until[uid] - now).total_seconds())} 秒后再试uwu~", d)
        return True
    elif uid in temp_ban_until:
        del temp_ban_until[uid]
    msg_times = user_message_history[uid]
    msg_times.append(now)
    while msg_times and (now - msg_times[0]).total_seconds() > TIME_WINDOW_SECONDS:
        msg_times.popleft()
    if len(msg_times) > MAX_MESSAGES:
        temp_ban_until[uid] = now + timedelta(seconds=BLOCK_DURATION_SECONDS)
        await post_floodgate_message(f"🧊你发送得太快啦，请 {BLOCK_DURATION_SECONDS} 秒后再试uwu~", d)
        return True
    return False

async def get_dau_history():
    if not os.path.exists(STAT_LOG):
        return "无历史统计数据"

    # 读取 JSON 文件
    with open(STAT_LOG, 'r', encoding='utf-8') as f:
        data = json.load(f)

    today = date.today()
    lines = []
    # 按顺序遍历所有天数（最旧到最新）
    for i in range(1, STAT_LOG_MAX_DAYS + 1):
        if str(i) not in data:
            continue
        entry = data[str(i)]
        entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        days_ago = (today - entry_date).days
        label = f"{days_ago}天前" if days_ago > 0 else "今天"
        lines.append(
            f"{entry_date.month}月{entry_date.day}日({label})：{entry['users']}用户 | {entry['calls']}调用"
        )
    return "\n".join(lines)