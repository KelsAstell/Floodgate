import json
import os
from datetime import datetime, timedelta

from config import log, VERSION, SUBSCRIPTION_VALIDITY_DAYS, SUBSCRIPTION_MESSAGE_FILE
from openapi.database import db_manager, pool


async def init_subscription_table():
    """初始化订阅表"""
    await db_manager.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            group_openid TEXT PRIMARY KEY,
            group_digit_id INTEGER,
            subscribed_at TEXT DEFAULT (datetime('now','localtime')),
            expires_at TEXT NOT NULL,
            subscribed_by TEXT
        )
    ''')


async def load_subscription_message() -> dict:
    """加载订阅消息模板，支持 {{date}} 和 {{version}} 占位符替换"""
    defaults = {
        "content": "这是默认的订阅推送消息。\n请在 `subscription_message.json` 中自定义内容。"
    }
    if not os.path.exists(SUBSCRIPTION_MESSAGE_FILE):
        log.warning(f"订阅消息文件 {SUBSCRIPTION_MESSAGE_FILE} 不存在，使用默认消息")
        return defaults
    try:
        with open(SUBSCRIPTION_MESSAGE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        log.error(f"加载订阅消息文件失败: {e}")
        return defaults


async def is_subscribed(group_openid: str) -> bool:
    """检查群是否已订阅（仅检查是否存在，不检查过期）"""
    query = db_manager.adapt_query(
        'SELECT 1 FROM subscriptions WHERE group_openid = ?'
    )
    async with pool.connection() as db:
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow(query, group_openid)
        else:
            cursor = await db.execute(query, (group_openid,))
            row = await cursor.fetchone()
            await cursor.close()
    return row is not None


async def _get_subscription_expiry(group_openid: str) -> str | None:
    """获取订阅过期时间字符串"""
    query = db_manager.adapt_query(
        'SELECT expires_at FROM subscriptions WHERE group_openid = ?'
    )
    async with pool.connection() as db:
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow(query, group_openid)
        else:
            cursor = await db.execute(query, (group_openid,))
            row = await cursor.fetchone()
            await cursor.close()
    return row[0] if row else None


async def subscribe_group(group_openid: str, group_digit_id: int, user_openid: str) -> tuple:
    """订阅群，返回 (是否成功, 消息文本)"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # SUBSCRIPTION_VALIDITY_DAYS 为 0 表示永不过期
    if SUBSCRIPTION_VALIDITY_DAYS > 0:
        expires_at = (datetime.now() + timedelta(days=SUBSCRIPTION_VALIDITY_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        validity_msg = f"有效期至 {expires_at}（{SUBSCRIPTION_VALIDITY_DAYS}天）。\n"
    else:
        expires_at = "2099-12-31 23:59:59"
        validity_msg = "订阅永久有效。\n"

    # 如果已存在记录，提示已订阅
    if await is_subscribed(group_openid):
        return False, f"本群已订阅！\n使用 ~subscribe renew 可续期，~unsubscribe 可取消订阅。"

    is_pg = db_manager.get_type() == "postgresql"
    async with pool.connection() as db:
        if is_pg:
            await db.execute(
                'INSERT INTO subscriptions (group_openid, group_digit_id, subscribed_at, expires_at, subscribed_by) '
                'VALUES ($1, $2, $3, $4, $5) '
                'ON CONFLICT(group_openid) DO UPDATE SET '
                'group_digit_id = $6, subscribed_at = $7, expires_at = $8, subscribed_by = $9',
                group_openid, group_digit_id, now_str, expires_at, user_openid,
                group_digit_id, now_str, expires_at, user_openid
            )
        else:
            await db.execute(
                'INSERT OR REPLACE INTO subscriptions '
                '(group_openid, group_digit_id, subscribed_at, expires_at, subscribed_by) '
                'VALUES (?, ?, ?, ?, ?)',
                (group_openid, group_digit_id, now_str, expires_at, user_openid)
            )
            await db.commit()

    log.success(f"群 {group_digit_id} 已订阅，有效期至 {expires_at}")
    return True, (
        f"订阅成功！每天早 8:00 将自动推送。\n"
        f"{validity_msg}"
        f"使用 ~subscribe renew 可续期，使用 ~unsubscribe 可取消订阅。"
    )


async def renew_subscription(group_openid: str, group_digit_id: int) -> tuple:
    """续期订阅，返回 (是否成功, 消息文本)"""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # 查询当前过期时间
    expiry = await _get_subscription_expiry(group_openid)
    if expiry is None:
        return False, "本群尚未订阅，请先使用 ~subscribe 订阅。"

    try:
        old_expires = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
    except Exception:
        old_expires = now

    # 从当前时间或原过期时间（取更晚的）开始续期
    base = max(now, old_expires)
    new_expires = base + timedelta(days=SUBSCRIPTION_VALIDITY_DAYS)
    new_expires_str = new_expires.strftime("%Y-%m-%d %H:%M:%S")

    is_pg = db_manager.get_type() == "postgresql"
    async with pool.connection() as db:
        if is_pg:
            await db.execute(
                'UPDATE subscriptions SET subscribed_at = $1, expires_at = $2 WHERE group_openid = $3',
                now_str, new_expires_str, group_openid
            )
        else:
            await db.execute(
                'UPDATE subscriptions SET subscribed_at = ?, expires_at = ? WHERE group_openid = ?',
                (now_str, new_expires_str, group_openid)
            )
            await db.commit()

    log.success(f"群 {group_digit_id} 已续期，有效期至 {new_expires_str}")
    return True, (
        f"续期成功！有效期至 {new_expires_str}（{SUBSCRIPTION_VALIDITY_DAYS}天）。"
    )


async def unsubscribe_group(group_openid: str, group_digit_id: int) -> tuple:
    """取消订阅，返回 (是否成功, 消息文本)"""
    expiry = await _get_subscription_expiry(group_openid)
    if expiry is None:
        return False, "本群尚未订阅，无需取消。"

    is_pg = db_manager.get_type() == "postgresql"
    async with pool.connection() as db:
        if is_pg:
            await db.execute(
                'DELETE FROM subscriptions WHERE group_openid = $1',
                group_openid
            )
        else:
            await db.execute(
                'DELETE FROM subscriptions WHERE group_openid = ?',
                (group_openid,)
            )
            await db.commit()

    log.success(f"群 {group_digit_id} 已取消订阅")
    return True, "已取消订阅。"


async def get_all_active_subscriptions() -> list:
    """获取所有订阅（不检查过期时间），返回 [(group_openid, group_digit_id, expires_at), ...]"""
    query = db_manager.adapt_query(
        'SELECT group_openid, group_digit_id, expires_at FROM subscriptions'
    )
    async with pool.connection() as db:
        if db_manager.get_type() == "postgresql":
            rows = await db.fetch(query)
        else:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            await cursor.close()
    return [(row[0], row[1], row[2]) for row in rows] if rows else []


async def cleanup_expired_subscriptions() -> int:
    """清理过期订阅，返回清理数量"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_pg = db_manager.get_type() == "postgresql"
    async with pool.connection() as db:
        if is_pg:
            result = await db.execute(
                'DELETE FROM subscriptions WHERE expires_at <= $1',
                now
            )
            # PostgreSQL execute 返回 "DELETE N" 字符串
            count = int(result.split()[-1]) if result else 0
        else:
            cursor = await db.execute(
                'DELETE FROM subscriptions WHERE expires_at <= ?',
                (now,)
            )
            await db.commit()
            count = cursor.rowcount if hasattr(cursor, 'rowcount') else 0
    if count:
        log.info(f"已清理 {count} 个过期订阅")
    return count


async def remove_group_subscription(group_openid: str):
    """当 bot 被移出群时，自动删除该群的订阅记录（不输出消息，仅清理）"""
    is_pg = db_manager.get_type() == "postgresql"
    async with pool.connection() as db:
        if is_pg:
            await db.execute(
                'DELETE FROM subscriptions WHERE group_openid = $1',
                group_openid
            )
        else:
            cursor = await db.execute(
                'DELETE FROM subscriptions WHERE group_openid = ?',
                (group_openid,)
            )
            await db.commit()
    log.info(f"Bot 被移出群 {group_openid}，已自动取消订阅")
