import datetime
import json
import os
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Any, List, Tuple, Dict
from contextlib import asynccontextmanager
from collections import defaultdict

from aiocache import cached, Cache

from config import (
    MIGRATE_IDS, log, TRANSPARENT_OPENID, IDMAP_INITIAL_ID, IDMAP_TTL,
    STAT_LOG, STAT_LOG_MAX_DAYS, ACHIEVEMENT_PERSIST,
    USER_AGREEMENT_REQUIRED, USER_AGREEMENT_VERSION,
    DATABASE_URL, DATABASE_TYPE
)

# ==================== 数据库抽象接口 ====================

class DatabaseBackend(ABC):
    """数据库后端抽象基类"""

    @abstractmethod
    async def init(self):
        """初始化数据库连接"""
        pass

    @abstractmethod
    async def close(self):
        """关闭数据库连接"""
        pass

    @abstractmethod
    @asynccontextmanager
    async def connection(self):
        """获取数据库连接上下文管理器"""
        pass

    @abstractmethod
    async def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        """执行SQL语句"""
        pass

    @abstractmethod
    async def executemany(self, query: str, params_list: List[Tuple]) -> Any:
        """批量执行SQL语句"""
        pass

    @abstractmethod
    def get_placeholder(self) -> str:
        """获取参数占位符（SQLite用?，PostgreSQL用%s）"""
        pass

    @abstractmethod
    def adapt_query(self, query: str) -> str:
        """适配不同数据库的SQL语法"""
        pass


# ==================== SQLite 后端实现 ====================

class SQLiteBackend(DatabaseBackend):
    """SQLite数据库后端 - 使用单连接模式避免并发锁定"""

    def __init__(self, db_name: str, pool_size: int = 10):
        self.db_name = db_name
        self._conn = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def init(self):
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            import aiosqlite
            # 使用单个共享连接
            self._conn = await aiosqlite.connect(self.db_name, timeout=3.0)
            # 启用 WAL 模式以提高并发性能
            await self._conn.execute('PRAGMA journal_mode=WAL')
            await self._conn.execute('PRAGMA synchronous=NORMAL')
            await self._conn.execute('PRAGMA busy_timeout=10000')
            await self._conn.commit()
            self._initialized = True

    @asynccontextmanager
    async def connection(self):
        if not self._initialized:
            await self.init()
        # 单连接模式下直接返回共享连接
        yield self._conn

    async def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        async with self._lock:
            cursor = await self._conn.execute(query, params or ())
            await self._conn.commit()
            return cursor

    async def executemany(self, query: str, params_list: List[Tuple]) -> Any:
        async with self._lock:
            cursor = await self._conn.executemany(query, params_list)
            await self._conn.commit()
            return cursor

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._initialized = False

    def get_placeholder(self) -> str:
        return "?"

    def adapt_query(self, query: str) -> str:
        # SQLite 原生支持 ? 占位符，无需转换
        return query


# ==================== PostgreSQL 后端实现 ====================

class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL数据库后端"""

    def __init__(self, database_url: str, pool_size: int = 20):
        self.database_url = database_url
        self.pool_size = pool_size
        self._pool = None
        self._initialized = False

    async def init(self):
        if self._initialized:
            return
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=self.pool_size,
                command_timeout=60,
                server_settings={
                    'jit': 'off'  # 关闭JIT以获得更稳定的性能
                }
            )
            self._initialized = True
            log.success(f"PostgreSQL连接池初始化成功，大小: {self.pool_size}")
        except ImportError:
            log.error("请先安装 asyncpg: pip install asyncpg")
            raise

    @asynccontextmanager
    async def connection(self):
        if not self._initialized:
            await self.init()
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        query = self.adapt_query(query)
        async with self.connection() as conn:
            return await conn.execute(query, *(params or ()))

    async def executemany(self, query: str, params_list: List[Tuple]) -> Any:
        query = self.adapt_query(query)
        async with self.connection() as conn:
            return await conn.executemany(query, params_list)

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._initialized = False

    def get_placeholder(self) -> str:
        return "$%s"

    def adapt_query(self, query: str) -> str:
        """将 SQLite 风格的 ? 转换为 PostgreSQL 风格的 $1, $2..."""
        import re
        counter = [0]
        def replace_placeholder(match):
            counter[0] += 1
            return f"${counter[0]}"
        return re.sub(r'\?', replace_placeholder, query)


# ==================== 数据库管理器 ====================

class DatabaseManager:
    """数据库管理器，统一管理不同后端"""

    def __init__(self):
        self._backend: Optional[DatabaseBackend] = None
        self._type: str = DATABASE_TYPE

    async def init(self):
        """初始化数据库"""
        if self._type == "postgresql":
            if not DATABASE_URL:
                raise ValueError("使用 PostgreSQL 需要配置 DATABASE_URL")
            self._backend = PostgreSQLBackend(DATABASE_URL)
        else:
            db_name = DATABASE_URL.replace("sqlite://", "") if DATABASE_URL else "storage.db"
            self._backend = SQLiteBackend(db_name)

        await self._backend.init()
        await self._init_tables()

    async def _init_tables(self):
        """初始化数据库表结构"""
        ph = self._backend.get_placeholder()

        if ACHIEVEMENT_PERSIST:
            await self._backend.execute(f'''
                CREATE TABLE IF NOT EXISTS achievement (
                    id TEXT PRIMARY KEY,
                    achievement TEXT
                )
            ''')

        if USER_AGREEMENT_REQUIRED:
            await self._backend.execute(f'''
                CREATE TABLE IF NOT EXISTS user_agreement (
                    user_id TEXT PRIMARY KEY,
                    agreed_version TEXT NOT NULL,
                    agreed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

        if not TRANSPARENT_OPENID:
            await self._backend.execute(f'''
                CREATE TABLE IF NOT EXISTS idmap (
                    union_id TEXT PRIMARY KEY,
                    digit_id INTEGER UNIQUE
                )
            ''')
            # PostgreSQL 使用不同的索引创建语法
            if self._type == "postgresql":
                await self._backend.execute('''
                    CREATE INDEX IF NOT EXISTS idx_digit_id ON idmap(digit_id)
                ''')
            await self._backend.execute(f'''
                CREATE TABLE IF NOT EXISTS usage (
                    digit_id INTEGER PRIMARY KEY,
                    usage_cnt INTEGER DEFAULT 0,
                    usage_today INTEGER DEFAULT 0
                )
            ''')
        else:
            await self._backend.execute(f'''
                CREATE TABLE IF NOT EXISTS usage (
                    union_id TEXT PRIMARY KEY,
                    usage_cnt INTEGER DEFAULT 0,
                    usage_today INTEGER DEFAULT 0
                )
            ''')

    @asynccontextmanager
    async def connection(self):
        async with self._backend.connection() as conn:
            yield conn

    async def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        return await self._backend.execute(query, params)

    async def executemany(self, query: str, params_list: List[Tuple]) -> Any:
        return await self._backend.executemany(query, params_list)

    async def close(self):
        if self._backend:
            await self._backend.close()

    def get_type(self) -> str:
        return self._type

    def adapt_query(self, query: str) -> str:
        return self._backend.adapt_query(query)


# 全局数据库管理器实例
db_manager = DatabaseManager()

# 兼容旧代码的 pool 接口
class PoolWrapper:
    """包装器，使新接口兼容旧代码"""

    def connection(self):
        return db_manager.connection()

    async def execute(self, query: str, params: Optional[Tuple] = None):
        return await db_manager.execute(query, params)

    async def close(self):
        await db_manager.close()

# 导出连接池大小常量供外部使用
POOL_SIZE = 20 if DATABASE_TYPE == "postgresql" else 10

pool = PoolWrapper()

async def init_db():
    """初始化数据库"""
    await db_manager.init()

    # 显示数据库状态信息
    await _show_db_status()

    # 处理 ids.json 迁移（仅 SQLite 模式）
    if MIGRATE_IDS and db_manager.get_type() == "sqlite":
        if TRANSPARENT_OPENID:
            log.warning("OpenID透传已启用，无法导入idmap映射表")
        else:
            ids_path = os.path.join(os.getcwd(), "ids.json")
            if os.path.exists(ids_path):
                await batch_insert_idmap_from_json(ids_path)
                log.success("导入idmap映射表成功")
            else:
                log.warning("未找到ids.json文件，跳过导入idmap映射表")

    log.success(f"数据库初始化成功 (后端: {db_manager.get_type()})")


async def _show_db_status():
    """显示数据库状态自检信息"""
    db_type = db_manager.get_type()

    if db_type == "sqlite":
        # 获取 SQLite 数据库文件路径
        db_url = DATABASE_URL if DATABASE_URL else "storage.db"
        db_path = db_url.replace("sqlite:///", "")

        async with pool.connection() as db:
            # 检查日志模式
            cursor = await db.execute('PRAGMA journal_mode')
            row = await cursor.fetchone()
            journal_mode = row[0].upper() if row else "UNKNOWN"

            # 检查同步模式
            cursor = await db.execute('PRAGMA synchronous')
            row = await cursor.fetchone()
            sync_mode = row[0] if row else "UNKNOWN"

            # 检查数据库文件大小
            try:
                db_size = os.path.getsize(db_path) / (1024 * 1024)  # MB
                size_str = f"{db_size:.2f} MB"
            except OSError:
                size_str = "未知"

        # 根据模式显示不同级别的日志
        if journal_mode == "WAL":
            log.success(f"[数据库自检] SQLite WAL模式已启用 | 同步模式: {sync_mode} | 文件大小: {size_str}")
        else:
            log.warning(f"[数据库自检] SQLite 当前模式: {journal_mode} | 同步模式: {sync_mode} | 文件大小: {size_str}")
            log.warning("[数据库自检] 建议使用 WAL 模式以获得更好的并发性能")
            log.info("[数据库自检] 自动启用 WAL 模式中...")

            # 自动尝试启用 WAL 模式
            async with pool.connection() as db:
                await db.execute('PRAGMA journal_mode=WAL')
                await db.execute('PRAGMA synchronous=NORMAL')

            # 再次检查
            async with pool.connection() as db:
                cursor = await db.execute('PRAGMA journal_mode')
                row = await cursor.fetchone()
                new_mode = row[0].upper() if row else "UNKNOWN"

            if new_mode == "WAL":
                log.success("[数据库自检] WAL模式启用成功！")
            else:
                log.error(f"[数据库自检] WAL模式启用失败，当前模式: {new_mode}")

    elif db_type == "postgresql":
        async with pool.connection() as db:
            # 获取 PostgreSQL 版本
            row = await db.fetchrow('SELECT version()')
            version = row[0] if row else "未知"

            # 获取连接数信息
            try:
                row = await db.fetchrow('SELECT count(*) FROM pg_stat_activity')
                connections = row[0] if row else 0
            except:
                connections = "未知"

        log.success(f"[数据库自检] PostgreSQL 已连接 | 版本: {version[:50]}...")
        log.info(f"[数据库自检] 当前连接数: {connections}")


async def close_db_pool():
    """关闭数据库连接池"""
    await pool.close()


async def add_achievement(user_id: str, achievement_id: int) -> bool:
    if not ACHIEVEMENT_PERSIST:
        return True
    async with pool.connection() as db:
        query = db_manager.adapt_query('SELECT achievement FROM achievement WHERE id = ?')
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow(query, user_id)
        else:
            cursor = await db.execute(query, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
        if row is None:
            achievement_list = [achievement_id]
            query = db_manager.adapt_query('INSERT INTO achievement (id, achievement) VALUES (?, ?)')
            if db_manager.get_type() == "postgresql":
                await db.execute(query, user_id, json.dumps(achievement_list))
            else:
                await db.execute(query, (user_id, json.dumps(achievement_list)))
            if db_manager.get_type() != "postgresql":
                await db.commit()
            return True
        try:
            achievement_list = json.loads(row[0]) if row[0] else []
            if not isinstance(achievement_list, list):
                achievement_list = []
        except json.JSONDecodeError:
            achievement_list = []
        if achievement_id in achievement_list:
            return False
        achievement_list.append(achievement_id)
        query = db_manager.adapt_query('UPDATE achievement SET achievement = ? WHERE id = ?')
        if db_manager.get_type() == "postgresql":
            await db.execute(query, json.dumps(achievement_list), user_id)
        else:
            await db.execute(query, (json.dumps(achievement_list), user_id))
        if db_manager.get_type() != "postgresql":
            await db.commit()
        return True


async def get_achievement_list(user_id: str):
    async with pool.connection() as db:
        query = db_manager.adapt_query('SELECT achievement FROM achievement WHERE id = ?')
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow(query, user_id)
        else:
            cursor = await db.execute(query, (user_id,))
            row = await cursor.fetchone()
            await cursor.close()

        if row is None:
            return []
        try:
            achievement_list = json.loads(row[0]) if row[0] else []
            if not isinstance(achievement_list, list):
                return []
            return [int(a) for a in achievement_list]
        except json.JSONDecodeError:
            return []


@cached(ttl=1800, cache=Cache.MEMORY)
async def get_achievement_stat() -> dict:
    """统计每个成就被多少比例的用户获得，缓存30分钟"""
    async with pool.connection() as db:
        if db_manager.get_type() == "postgresql":
            rows = await db.fetch('SELECT achievement FROM achievement')
        else:
            cursor = await db.execute('SELECT achievement FROM achievement')
            rows = await cursor.fetchall()
            await cursor.close()

    total_users = len(rows)
    if total_users == 0:
        return {"total_users": 0, "stats": {}}

    count_map = defaultdict(int)
    for row in rows:
        try:
            achievement_list = json.loads(row[0]) if row[0] else []
            if not isinstance(achievement_list, list):
                continue
            for ach_id in achievement_list:
                count_map[int(ach_id)] += 1
        except (json.JSONDecodeError, ValueError):
            continue

    stats = {
        str(ach_id): round(count / total_users * 100, 2)
        for ach_id, count in sorted(count_map.items())
    }
    return {"total_users": total_users, "stats": stats}

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

    # 根据数据库类型选择正确的 SQL 语法
    if db_manager.get_type() == "postgresql":
        query = 'INSERT INTO idmap (union_id, digit_id) VALUES ($1, $2) ON CONFLICT DO NOTHING'
    else:
        query = 'INSERT OR IGNORE INTO idmap (union_id, digit_id) VALUES (?, ?)'

    async with pool.connection() as db:
        await db.executemany(query, purified_data)
        if db_manager.get_type() == "sqlite":
            await db.commit()



# ID生成锁，防止并发冲突
_id_generation_lock = asyncio.Lock()

@cached(ttl=IDMAP_TTL, cache=Cache.MEMORY)  # 缓存1小时
async def get_or_create_digit_id(union_id: str) -> int:
    if not union_id:
        return 0
    async with _id_generation_lock:
        async with pool.connection() as db:
            # 检查是否已存在
            query = db_manager.adapt_query('SELECT digit_id FROM idmap WHERE union_id=?')
            if db_manager.get_type() == "postgresql":
                row = await db.fetchrow(query, union_id)
                if row:
                    return row[0]
                row = await db.fetchrow('SELECT MAX(digit_id) FROM idmap')
                max_digit_id = row[0] or IDMAP_INITIAL_ID
                # 直接使用 MAX + 1，无需循环查找
                next_digit_id = max_digit_id + 1
                query = db_manager.adapt_query('INSERT INTO idmap (union_id, digit_id) VALUES (?, ?)')
                await db.execute(query, union_id, next_digit_id)
            else:
                cursor = await db.execute(query, (union_id,))
                row = await cursor.fetchone()
                await cursor.close()
                if row:
                    return row[0]
                cursor = await db.execute('SELECT MAX(digit_id) FROM idmap')
                row = await cursor.fetchone()
                await cursor.close()
                max_digit_id = row[0] or IDMAP_INITIAL_ID
                # 直接使用 MAX + 1，无需循环查找
                next_digit_id = max_digit_id + 1
                query = db_manager.adapt_query('INSERT INTO idmap (union_id, digit_id) VALUES (?, ?)')
                await db.execute(query, (union_id, next_digit_id))
                await db.commit()
            return next_digit_id

@cached(ttl=IDMAP_TTL, cache=Cache.MEMORY)
async def get_union_id_by_digit_id(digit_id: int) -> str:
    async with pool.connection() as db:
        query = db_manager.adapt_query('SELECT union_id FROM idmap WHERE digit_id=?')
        if db_manager.get_type() == "postgresql":
            # asyncpg 使用 fetchrow 直接获取单行数据
            row = await db.fetchrow(query, digit_id)
            return row[0] if row else None
        else:
            # aiosqlite 使用 execute + fetchone
            cursor = await db.execute(query, (digit_id,))
            row = await cursor.fetchone()
            await cursor.close()
            return row[0] if row else None


# 使用量统计（内存缓存）
_pending_counts = {}
_flush_lock = asyncio.Lock()


async def increment_usage(id_val):
    """增加使用量（内存中）"""
    if id_val not in _pending_counts:
        _pending_counts[id_val] = 0
    _pending_counts[id_val] += 1
    return True

async def get_pending_counts():
    return len(dict(_pending_counts))

async def flush_usage_to_db():
    """刷新使用量到数据库"""
    global _pending_counts
    async with _flush_lock:
        if not _pending_counts:
            return
        to_write = dict(_pending_counts)
        _pending_counts.clear()

        # 根据数据库类型选择 SQL 语法
        is_pg = db_manager.get_type() == "postgresql"

        async with pool.connection() as db:
            for id_val, count in to_write.items():
                if TRANSPARENT_OPENID:
                    if is_pg:
                        await db.execute('''
                            INSERT INTO usage (union_id, usage_cnt, usage_today)
                            VALUES ($1, $2, $3)
                            ON CONFLICT(union_id) DO UPDATE SET
                                usage_cnt = usage.usage_cnt + $4,
                                usage_today = usage.usage_today + $5
                        ''', id_val, count, count, count, count)
                    else:
                        await db.execute('''
                            INSERT INTO usage (union_id, usage_cnt, usage_today)
                            VALUES (?, ?, ?)
                            ON CONFLICT(union_id) DO UPDATE SET
                                usage_cnt = usage_cnt + ?,
                                usage_today = usage_today + ?
                        ''', (id_val, count, count, count, count))
                else:
                    if is_pg:
                        await db.execute('''
                            INSERT INTO usage (digit_id, usage_cnt, usage_today)
                            VALUES ($1, $2, $3)
                            ON CONFLICT(digit_id) DO UPDATE SET
                                usage_cnt = usage.usage_cnt + $4,
                                usage_today = usage.usage_today + $5
                        ''', id_val, count, count, count, count)
                    else:
                        await db.execute('''
                            INSERT INTO usage (digit_id, usage_cnt, usage_today)
                            VALUES (?, ?, ?)
                            ON CONFLICT(digit_id) DO UPDATE SET
                                usage_cnt = usage_cnt + ?,
                                usage_today = usage_today + ?
                        ''', (id_val, count, count, count, count))
            if not is_pg:
                await db.commit()
            log.debug(f"已批量刷新 {len(to_write)} 条 usage 记录到数据库")


async def reset_usage_today():
    is_pg = db_manager.get_type() == "postgresql"

    async with pool.connection() as db:
        if is_pg:
            row = await db.fetchrow('SELECT COUNT(*), SUM(usage_today) FROM usage WHERE usage_today > 0')
            used_count = row[0] or 0
            total_calls = row[1] or 0
            await db.execute('UPDATE usage SET usage_today = 0 WHERE usage_today != 0')
        else:
            cursor = await db.execute('SELECT COUNT(*), SUM(usage_today) FROM usage WHERE usage_today > 0')
            row = await cursor.fetchone()
            used_count = row[0] or 0
            total_calls = row[1] or 0
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
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow('SELECT COUNT(*), SUM(usage_today) FROM usage WHERE usage_today > 0')
        else:
            cursor = await db.execute('SELECT COUNT(*), SUM(usage_today) FROM usage WHERE usage_today > 0')
            row = await cursor.fetchone()
            await cursor.close()
        dau = row[0] if row else 0
        dai = row[1] if row and row[1] is not None else 0
        return {
            "dau": dau,  # Daily Active Users
            "dai": dai   # Daily Active Invocations (calls)
        }

@cached(ttl=60, cache=Cache.MEMORY)
async def get_usage_count(id_val) -> int:
    """获取使用量"""
    async with pool.connection() as db:
        if TRANSPARENT_OPENID:
            query = db_manager.adapt_query('SELECT usage_cnt FROM usage WHERE union_id=?')
        else:
            query = db_manager.adapt_query('SELECT usage_cnt FROM usage WHERE digit_id=?')
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow(query, id_val)
        else:
            cursor = await db.execute(query, (id_val,))
            row = await cursor.fetchone()
            await cursor.close()
        return row[0] if row else 0


# ==================== 用户协议同意相关操作 ====================

# 用户协议缓存 TTL（秒）
USER_AGREEMENT_CACHE_TTL = 1800  # 30分钟

@cached(ttl=USER_AGREEMENT_CACHE_TTL, cache=Cache.MEMORY)
async def check_user_agreement(user_id: str, required_version: str) -> bool:
    """
    检查用户是否已同意指定版本的协议
    
    Args:
        user_id: 用户ID
        required_version: 要求的协议版本
        
    Returns:
        bool: 是否已同意该版本协议
    """
    if not USER_AGREEMENT_REQUIRED:
        return True
    
    async with pool.connection() as db:
        query = db_manager.adapt_query('SELECT agreed_version FROM user_agreement WHERE user_id = ?')
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow(query, str(user_id))
        else:
            cursor = await db.execute(query, (str(user_id),))
            row = await cursor.fetchone()
            await cursor.close()
        if not row:
            return False
        # 检查版本是否匹配（要求完全匹配）
        return row[0] == required_version


async def set_user_agreement(user_id: str, version: str) -> bool:
    """
    设置用户同意协议

    Args:
        user_id: 用户ID
        version: 协议版本

    Returns:
        bool: 是否设置成功
    """
    if not USER_AGREEMENT_REQUIRED:
        return True

    try:
        is_pg = db_manager.get_type() == "postgresql"

        async with pool.connection() as db:
            if is_pg:
                await db.execute(
                    '''INSERT INTO user_agreement (user_id, agreed_version, agreed_at)
                       VALUES ($1, $2, NOW())
                       ON CONFLICT(user_id) DO UPDATE SET
                       agreed_version = $3, agreed_at = NOW()''',
                    str(user_id), version, version
                )
            else:
                await db.execute(
                    '''INSERT INTO user_agreement (user_id, agreed_version, agreed_at)
                       VALUES (?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET
                       agreed_version = ?, agreed_at = CURRENT_TIMESTAMP''',
                    (str(user_id), version, version)
                )
                await db.commit()

            # 清除该用户的协议缓存（针对所有可能的版本要求）
            cache = Cache(Cache.MEMORY)
            cache_key = f"check_user_agreement:{str(user_id)}:{USER_AGREEMENT_VERSION}"
            await cache.delete(cache_key)

            return True
    except Exception as e:
        log.error(f"设置用户协议同意状态失败: {e}")
        return False


async def get_user_agreement_status(user_id: str) -> dict:
    """
    获取用户协议同意状态
    
    Args:
        user_id: 用户ID
        
    Returns:
        dict: 包含 agreed_version 和 agreed_at 的字典，未同意则返回空值
    """
    if not USER_AGREEMENT_REQUIRED:
        return {"agreed": True, "version": None, "agreed_at": None}
    
    async with pool.connection() as db:
        query = db_manager.adapt_query('SELECT agreed_version, agreed_at FROM user_agreement WHERE user_id = ?')
        if db_manager.get_type() == "postgresql":
            row = await db.fetchrow(query, str(user_id))
        else:
            cursor = await db.execute(query, (str(user_id),))
            row = await cursor.fetchone()
            await cursor.close()
        if row:
            return {
                "agreed": True,
                "version": row[0],
                "agreed_at": row[1]
            }
        return {"agreed": False, "version": None, "agreed_at": None}

