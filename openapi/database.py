import datetime
import json
import os
import aiosqlite
from aiocache import cached, Cache
from collections import defaultdict
from contextlib import asynccontextmanager
import asyncio
from config import MIGRATE_IDS, log, TRANSPARENT_OPENID, IDMAP_INITIAL_ID, IDMAP_TTL, STAT_LOG, STAT_LOG_MAX_DAYS, \
    ACHIEVEMENT_PERSIST

DB_NAME = 'storage.db'
POOL_SIZE = 10

# 创建连接池
class ConnectionPool:
    def __init__(self, db_name, pool_size):
        self.db_name = db_name
        self.pool_size = pool_size
        self._queue = None
        self._initialized = False

    async def init(self):
        if self._initialized:
            return
        self._queue = asyncio.Queue()
        for _ in range(self.pool_size):
            conn = await aiosqlite.connect(self.db_name)
            await self._queue.put(conn)
        self._initialized = True

    @asynccontextmanager
    async def connection(self):
        if not self._initialized:
            await self.init()
        conn = await self._queue.get()
        try:
            yield conn
        finally:
            await self._queue.put(conn)

    async def execute(self, query, params=None):
        async with self.connection() as conn:
            cursor = await conn.execute(query, params or ())
            await conn.commit()
            return cursor

    async def close(self):
        if self._queue:
            while not self._queue.empty():
                conn = await self._queue.get()
                await conn.close()
            self._initialized = False

pool = ConnectionPool(DB_NAME, POOL_SIZE)

async def init_db():
    if os.path.exists(DB_NAME):
        if ACHIEVEMENT_PERSIST:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute('''
                CREATE TABLE IF NOT EXISTS achievement (
                    id TEXT PRIMARY KEY,
                    achievement TEXT
                )
            ''')
        await pool.init()  # 初始化连接池
        return
    async with aiosqlite.connect(DB_NAME) as db:
        if ACHIEVEMENT_PERSIST:
            await db.execute('''
            CREATE TABLE IF NOT EXISTS achievement (
                id TEXT PRIMARY KEY,
                achievement TEXT
            )
        ''')
        if not TRANSPARENT_OPENID:
            await db.execute('''
            CREATE TABLE IF NOT EXISTS idmap (
                union_id TEXT PRIMARY KEY, 
                digit_id INTEGER UNIQUE
            )
        ''')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_digit_id ON idmap(digit_id)')
            log.success("idmap映射表创建成功")
            await db.execute('''
                CREATE TABLE IF NOT EXISTS usage (
                    digit_id INTEGER PRIMARY KEY,
                    usage_cnt INTEGER DEFAULT 0,
                    usage_today INTEGER DEFAULT 0
                ) WITHOUT ROWID
            ''')
        else:
            log.warning("OpenID透传已启用，不创建idmap映射表")
            await db.execute('''
                CREATE TABLE IF NOT EXISTS usage (
                    union_id TEXT PRIMARY KEY,
                    usage_cnt INTEGER DEFAULT 0,
                    usage_today INTEGER DEFAULT 0
                ) WITHOUT ROWID
            ''')
        await db.commit()
    log.success("数据库创建成功")
    ids_path = os.path.join(os.getcwd(), "ids.json")
    if MIGRATE_IDS:
        if TRANSPARENT_OPENID:
            log.warning("OpenID透传已启用，无法导入idmap映射表")
        if not os.path.exists(ids_path):
            log.warning("未找到ids.json文件，跳过导入idmap映射表")
            await pool.init()  # 初始化连接池
            return
        await batch_insert_idmap_from_json(ids_path)
        log.success("导入idmap映射表成功")
    await pool.init()  # 初始化连接池


async def close_db_pool():
    """关闭数据库连接池"""
    await pool.close()


async def add_achievement(user_id: str, achievement_id: int) -> bool:
    if not ACHIEVEMENT_PERSIST:
        return True
    async with pool.connection() as db:
        cursor = await db.execute(
            'SELECT achievement FROM achievement WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row is None:
            achievement_list = [achievement_id]
            await db.execute(
                'INSERT INTO achievement (id, achievement) VALUES (?, ?)',
                (user_id, json.dumps(achievement_list))
            )
            await db.commit()
            return True
        try:
            achievement_list = json.loads(row[0]) if row[0] else []
            if not isinstance(achievement_list, list):
                achievement_list = []
        except json.JSONDecodeError:
            achievement_list = []
        #achievement_list = [int(a) for a in achievement_list]
        if achievement_id in achievement_list:
            return False
        achievement_list.append(achievement_id)
        await db.execute(
            'UPDATE achievement SET achievement = ? WHERE id = ?',
            (json.dumps(achievement_list), user_id)
        )
        await db.commit()
        return True


async def get_achievement_list(user_id: str):
    async with pool.connection() as db:
        cursor = await db.execute(
            'SELECT achievement FROM achievement WHERE id = ?', (user_id,)
        )
        row = await cursor.fetchone()

        if row is None:
            return []
        try:
            achievement_list = json.loads(row[0]) if row[0] else []
            if not isinstance(achievement_list, list):
                return []
            return [int(a) for a in achievement_list]
        except json.JSONDecodeError:
            return []

async def batch_insert_idmap_from_json(ids_path):
    import base64
    import json
    import struct
    def decode_key(encoded_key):
        decoded = base64.b64decode(encoded_key)
        try:
            return decoded.decode('utf-8')
        except UnicodeDecodeError:
            return decoded

    def decode_value(encoded_value):
        """尝试将 value 解码为 uint64 整数，否则返回原始字节或 base64 字符串"""
        decoded = base64.b64decode(encoded_value)
        if len(decoded) == 8:
            try:
                return struct.unpack('>Q', decoded)[0]  # 大端序解析
            except struct.error:
                pass
        return decoded
    with open(ids_path, 'r', encoding='utf-8') as f:
        data_list = json.load(f)

    decoded_data = [
        (decode_key(item['key']), decode_value(item['value']))
        for item in data_list
    ]

    purified_data = [(key, value) for key, value in decoded_data if len(key)==32]
    async with pool.connection() as db:
        await db.executemany(
            'INSERT OR IGNORE INTO idmap (union_id, digit_id) VALUES (?, ?)',
            purified_data
        )
        await db.commit()



@cached(ttl=IDMAP_TTL, cache=Cache.MEMORY)  # 缓存1小时
async def get_or_create_digit_id(union_id: str) -> int:
    if not union_id:
        return 0
    async with pool.connection() as db:
        # 检查是否已存在
        async with db.execute('SELECT digit_id FROM idmap WHERE union_id=?', (union_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
        async with db.execute('SELECT MAX(digit_id) FROM idmap') as cursor:
            row = await cursor.fetchone()
            max_digit_id = row[0] or IDMAP_INITIAL_ID

        # 直接使用 MAX + 1，无需循环查找
        next_digit_id = max_digit_id + 1
        await db.execute('INSERT INTO idmap (union_id, digit_id) VALUES (?, ?)',
                         (union_id, next_digit_id))
        await db.commit()
        return next_digit_id

@cached(ttl=IDMAP_TTL, cache=Cache.MEMORY)
async def get_union_id_by_digit_id(digit_id: int) -> str:
    async with pool.connection() as db:
        async with db.execute('SELECT union_id FROM idmap WHERE digit_id=?', (digit_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


# 更新内存缓存
async def increment_usage(id):
    global _pending_counts
    _pending_counts[id] += 1
    return True


_pending_counts = defaultdict(int)
_flush_lock = asyncio.Lock()

async def get_pending_counts():
    return len(dict(_pending_counts))
async def flush_usage_to_db():
    global _pending_counts
    async with _flush_lock:
        if not _pending_counts:
            return
        to_write = dict(_pending_counts)
        _pending_counts.clear()
        async with pool.connection() as db:
            for id, count in to_write.items():
                if TRANSPARENT_OPENID:
                    await db.execute('''
                        INSERT INTO usage (union_id, usage_cnt, usage_today)
                        VALUES (?, ?, ?)
                        ON CONFLICT(union_id) DO UPDATE SET
                            usage_cnt = usage_cnt + ?,
                            usage_today = usage_today + ?
                    ''', (id, count, count, count, count))
                else:
                    await db.execute('''
                        INSERT INTO usage (digit_id, usage_cnt, usage_today)
                        VALUES (?, ?, ?)
                        ON CONFLICT(digit_id) DO UPDATE SET
                            usage_cnt = usage_cnt + ?,
                            usage_today = usage_today + ?
                    ''', (id, count, count, count, count))
            await db.commit()
            log.debug(f"已批量刷新 {len(to_write)} 条 usage 记录到数据库")


async def reset_usage_today():
    async with pool.connection() as db:
        cursor = await db.execute('SELECT COUNT(*), SUM(usage_today) FROM usage WHERE usage_today > 0')
        row = await cursor.fetchone()
        used_count = row[0] or 0
        total_calls = row[1] or 0  # 避免 None
        await db.execute('UPDATE usage SET usage_today = 0 WHERE usage_today != 0')
        await db.commit()
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    if os.path.exists(STAT_LOG):
        with open(STAT_LOG, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
    else:
        old_data = {}
    new_entry = {
        "date": str(yesterday),
        "users": used_count,
        "calls": total_calls
    }
    data = {}
    keys = sorted([int(k) for k in old_data.keys() if k.isdigit()])
    for k in keys:
        new_key = k - 1
        if new_key < 1:
            continue
        data[str(new_key)] = old_data[str(k)]
    data[str(STAT_LOG_MAX_DAYS)] = new_entry
    with open(STAT_LOG, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.success(f"已重置今日使用统计数据（保存最近 {STAT_LOG_MAX_DAYS} 天")


@cached(ttl=60, cache=Cache.MEMORY)
async def get_dau_today() -> dict:
    async with pool.connection() as db:
        async with db.execute('SELECT COUNT(*), SUM(usage_today) FROM usage WHERE usage_today > 0') as cursor:
            row = await cursor.fetchone()
            dau = row[0] if row else 0
            dai = row[1] if row and row[1] is not None else 0
            return {
                "dau": dau,  # Daily Active Users
                "dai": dai   # Daily Active Invocations (calls)
            }

@cached(ttl=60, cache=Cache.MEMORY)
async def get_usage_count(id) -> int:
    async with pool.connection() as db:
        if TRANSPARENT_OPENID:
            async with db.execute('SELECT usage_cnt FROM usage WHERE union_id=?', (id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        else:
            async with db.execute('SELECT usage_cnt FROM usage WHERE digit_id=?', (id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

