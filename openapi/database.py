import os
import aiosqlite
from aiocache import cached, Cache
from contextlib import asynccontextmanager
import asyncio

from config import MIGRATE_IDS, log, TRANSPARENT_OPENID

DB_NAME = 'storage.db'
INITIAL_DIGIT_ID = 100000
POOL_SIZE = 5

# 创建连接池
class ConnectionPool:
    def __init__(self, db_name, pool_size):
        self.db_name = db_name
        self.pool_size = pool_size
        self._queue = None

    async def init(self):
        self._queue = asyncio.Queue()
        for _ in range(self.pool_size):
            conn = await aiosqlite.connect(self.db_name)
            await self._queue.put(conn)

    @asynccontextmanager
    async def connection(self):
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

pool = ConnectionPool(DB_NAME, POOL_SIZE)

async def init_db():
    if os.path.exists(DB_NAME):
        return
    async with aiosqlite.connect(DB_NAME) as db:
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
                    usage_cnt INTEGER DEFAULT 0
                ) WITHOUT ROWID
            ''')
        else:
            log.warning("OpenID透传已启用，不创建idmap映射表")
            await db.execute('''
                CREATE TABLE IF NOT EXISTS usage (
                    union_id TEXT PRIMARY KEY,
                    usage_cnt INTEGER DEFAULT 0
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
            return
        await batch_insert_idmap_from_json(ids_path)
        log.success("导入idmap映射表成功")

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
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executemany(
            'INSERT OR IGNORE INTO idmap (union_id, digit_id) VALUES (?, ?)',
            purified_data
        )
        await db.commit()



@cached(ttl=3600, cache=Cache.MEMORY)  # 缓存1小时
async def get_or_create_digit_id(union_id: str) -> int:
    if not union_id:
        return 0
    async with aiosqlite.connect(DB_NAME) as db:
        # 检查是否已存在
        async with db.execute('SELECT digit_id FROM idmap WHERE union_id=?', (union_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
        async with db.execute('SELECT MAX(digit_id) FROM idmap') as cursor:
            row = await cursor.fetchone()
            max_digit_id = row[0] or INITIAL_DIGIT_ID

        # 寻找下一个可用的digit_id
        next_digit_id = max_digit_id + 1
        while True:
            async with db.execute('SELECT 1 FROM idmap WHERE digit_id=?', (next_digit_id,)) as cursor:
                if not await cursor.fetchone():
                    break
            next_digit_id += 1
        await db.execute('INSERT INTO idmap (union_id, digit_id) VALUES (?, ?)',
                         (union_id, next_digit_id))
        await db.commit()
        return next_digit_id

@cached(ttl=3600, cache=Cache.MEMORY)
async def get_union_id_by_digit_id(digit_id: int) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT union_id FROM idmap WHERE digit_id=?', (digit_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


# 无需实时更新缓存，更轻量
async def increment_usage(id):
    async with aiosqlite.connect(DB_NAME) as db:
        if TRANSPARENT_OPENID:
            await db.execute('''
                INSERT INTO usage (union_id, usage_cnt)
                VALUES (?, 1)
                ON CONFLICT(union_id) DO UPDATE SET
                    usage_cnt = usage_cnt + 1
            ''', (id,))
        else:
            await db.execute('''
                    INSERT INTO usage (digit_id, usage_cnt)
                    VALUES (?, 1)
                    ON CONFLICT(digit_id) DO UPDATE SET
                        usage_cnt = usage_cnt + 1
                ''', (id,))
        await db.commit()
        return True


@cached(ttl=60, cache=Cache.MEMORY)
async def get_usage_count(id) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        if TRANSPARENT_OPENID:
            async with db.execute('SELECT usage_cnt FROM usage WHERE union_id=?', (id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        else:
            async with db.execute('SELECT usage_cnt FROM usage WHERE digit_id=?', (id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

