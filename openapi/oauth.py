import secrets
import sqlite3
import string
import threading
from datetime import datetime, timedelta


import jwt
from cachetools import TTLCache

from config import BOT_SECRET, OAUTH_LOGIN_TOKEN_TTL, OAUTH_JWT_EXPIRY_DAYS, OAUTH_LOGIN_TOKEN_LENGTH, log


class OAuthManager:
    """OAuth 登录管理器，处理令牌生成、JWT签发和验证

    JWT 会话持久化到 SQLite（oauth_sessions.db）：
    - bot 重启后内存缓存清空，但会话可从数据库恢复，已签发的 JWT 不会因此失效
    - 单点登录/撤销同样持久化，防止 bot 重启后已被撤销的 JWT 重新生效
    """

    def __init__(self, sessions_db: str | None = None):
        # 登录令牌缓存 (TTL=5分钟)
        self._login_token_cache: TTLCache = TTLCache(
            maxsize=1000, 
            ttl=OAUTH_LOGIN_TOKEN_TTL
        )
        # JWT会话缓存，仅作为内存加速层，TTL与JWT有效期一致
        self._jwt_session_cache: TTLCache = TTLCache(
            maxsize=10000, 
            ttl=OAUTH_JWT_EXPIRY_DAYS * 24 * 3600
        )
        # 用户JWT映射（用于单点登录）
        self._user_jwt_map: dict = {}
        # JWT签名密钥
        self._jwt_secret = BOT_SECRET
        # 令牌字符集
        self._token_chars = string.ascii_letters + string.digits
        # 登录令牌长度
        self._token_length = OAUTH_LOGIN_TOKEN_LENGTH
        # 会话持久化（SQLite，独立于主数据库，便于同步调用）
        self._sessions_db = sessions_db or "oauth_sessions.db"
        self._db_lock = threading.Lock()
        self._init_sessions_db()
        self._load_sessions_from_db()

    # ---------- 会话持久化 ----------

    def _init_sessions_db(self):
        """初始化会话表并清理已过期会话"""
        try:
            with self._db_lock:
                with sqlite3.connect(self._sessions_db, timeout=5.0) as conn:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS oauth_sessions (
                            jwt_token TEXT PRIMARY KEY,
                            union_openid TEXT NOT NULL,
                            exp_ts REAL NOT NULL,
                            active INTEGER NOT NULL DEFAULT 1
                        )
                    """)
                    conn.execute(
                        "DELETE FROM oauth_sessions WHERE exp_ts <= ?",
                        (datetime.utcnow().timestamp(),)
                    )
                    conn.commit()
        except Exception as e:
            log.error(f"[OAuth] 初始化会话数据库失败: {e}")

    def _load_sessions_from_db(self):
        """启动时将未过期的有效会话恢复到内存缓存"""
        try:
            with self._db_lock:
                with sqlite3.connect(self._sessions_db, timeout=5.0) as conn:
                    rows = conn.execute(
                        "SELECT jwt_token, union_openid FROM oauth_sessions WHERE active = 1 AND exp_ts > ?",
                        (datetime.utcnow().timestamp(),)
                    ).fetchall()
            restored = 0
            for jwt_token, union_openid in rows:
                if jwt_token in self._jwt_session_cache:
                    continue
                self._jwt_session_cache[jwt_token] = union_openid
                self._user_jwt_map[union_openid] = jwt_token
                restored += 1
            if restored:
                log.info(f"[OAuth] 从数据库恢复 {restored} 个JWT会话")
        except Exception as e:
            log.error(f"[OAuth] 恢复JWT会话失败: {e}")

    def _save_session(self, jwt_token: str, union_openid: str, exp_ts: float):
        """持久化新会话，并撤销该用户的其他会话（单点登录）"""
        try:
            with self._db_lock:
                with sqlite3.connect(self._sessions_db, timeout=5.0) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO oauth_sessions (jwt_token, union_openid, exp_ts, active) VALUES (?, ?, ?, 1)",
                        (jwt_token, union_openid, exp_ts)
                    )
                    conn.execute(
                        "UPDATE oauth_sessions SET active = 0 WHERE union_openid = ? AND jwt_token <> ?",
                        (union_openid, jwt_token)
                    )
                    conn.execute(
                        "DELETE FROM oauth_sessions WHERE exp_ts <= ?",
                        (datetime.utcnow().timestamp(),)
                    )
                    conn.commit()
        except Exception as e:
            log.error(f"[OAuth] 持久化JWT会话失败: {e}")

    def _deactivate_session(self, jwt_token: str):
        """持久化撤销会话"""
        try:
            with self._db_lock:
                with sqlite3.connect(self._sessions_db, timeout=5.0) as conn:
                    conn.execute(
                        "UPDATE oauth_sessions SET active = 0 WHERE jwt_token = ?",
                        (jwt_token,)
                    )
                    conn.commit()
        except Exception as e:
            log.error(f"[OAuth] 撤销JWT会话失败: {e}")

    def _query_session(self, jwt_token: str) -> tuple | None:
        """查询会话记录: (jwt_token, union_openid, exp_ts, active)"""
        try:
            with self._db_lock:
                with sqlite3.connect(self._sessions_db, timeout=5.0) as conn:
                    row = conn.execute(
                        "SELECT jwt_token, union_openid, exp_ts, active FROM oauth_sessions WHERE jwt_token = ?",
                        (jwt_token,)
                    ).fetchone()
            return row
        except Exception as e:
            log.error(f"[OAuth] 查询JWT会话失败: {e}")
            return None
    
    def generate_login_token(self, union_openid: str) -> str:
        """生成登录令牌
        
        Args:
            union_openid: 用户的union_openid
            
        Returns:
            随机登录令牌字符串
        """
        token = ''.join(secrets.choice(self._token_chars) for _ in range(self._token_length))
        self._login_token_cache[token] = union_openid
        log.debug(f"[OAuth] 为用户 {union_openid[:8]}... 生成登录令牌")
        return token
    
    def verify_login_token(self, token: str) -> str | None:
        """验证并消费登录令牌（一次性使用）
        
        Args:
            token: 登录令牌
            
        Returns:
            验证成功返回union_openid，失败返回None
        """
        union_openid = self._login_token_cache.pop(token, None)
        if union_openid:
            log.info(f"[OAuth] 登录令牌验证成功，用户: {union_openid[:8]}...")
        else:
            log.warning(f"[OAuth] 登录令牌验证失败: {token}")
        return union_openid
    
    def create_jwt(self, union_openid: str) -> tuple[str, int]:
        """创建JWT令牌，同时使该用户的旧JWT失效（单点登录，内存+数据库双撤销）"""
        # 使旧JWT失效（单点登录）
        old_jwt = self._user_jwt_map.get(union_openid)
        if old_jwt and old_jwt in self._jwt_session_cache:
            del self._jwt_session_cache[old_jwt]
            log.debug(f"[OAuth] 用户 {union_openid[:8]}... 的旧JWT已失效")
        
        # 创建新JWT
        now = datetime.utcnow()
        expires_in = OAUTH_JWT_EXPIRY_DAYS * 24 * 3600
        exp = now + timedelta(days=OAUTH_JWT_EXPIRY_DAYS)
        
        payload = {
            "union_openid": union_openid,
            "iat": now,
            "exp": exp
        }
        
        jwt_token = jwt.encode(payload, self._jwt_secret, algorithm="HS256")
        
        # 存储JWT会话（内存 + 数据库；数据库侧同时撤销该用户其他会话）
        self._jwt_session_cache[jwt_token] = union_openid
        self._user_jwt_map[union_openid] = jwt_token
        self._save_session(jwt_token, union_openid, exp.timestamp())
        
        log.info(f"[OAuth] 为用户 {union_openid[:8]}... 签发JWT，有效期{OAUTH_JWT_EXPIRY_DAYS}天")
        return jwt_token, expires_in
    
    def verify_jwt(self, token: str) -> str | None:
        """验证JWT令牌
        
        优先走内存缓存；缓存 miss（如 bot 重启后）回查持久化会话，
        签名有效且未被撤销的会话自动恢复，已签发的 JWT 不会因重启而失效。
        
        Args:
            token: JWT令牌
            
        Returns:
            验证成功返回union_openid，失败返回None
        """
        # 快速路径：内存缓存命中（未撤销）
        if token in self._jwt_session_cache:
            try:
                payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
                union_openid = payload.get("union_openid")
                if union_openid:
                    return union_openid
                log.warning(f"[OAuth] JWT payload中缺少union_openid")
                return None
            except jwt.ExpiredSignatureError:
                log.warning(f"[OAuth] JWT已过期")
                self._jwt_session_cache.pop(token, None)
                return None
            except jwt.InvalidTokenError as e:
                log.warning(f"[OAuth] JWT验证失败: {e}")
                return None
        
        # 内存 miss：回查持久化会话（处理 bot 重启后缓存丢失的情况）
        row = self._query_session(token)
        if not row:
            log.warning(f"[OAuth] JWT不在会话中（可能从未签发或已被撤销）")
            return None
        _jwt_token, union_openid, _exp_ts, active = row
        if not active:
            log.warning(f"[OAuth] JWT已被撤销")
            return None
        
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            union_openid = payload.get("union_openid")
            if not union_openid:
                log.warning(f"[OAuth] JWT payload中缺少union_openid")
                return None
            # 恢复会话到内存缓存
            self._jwt_session_cache[token] = union_openid
            self._user_jwt_map[union_openid] = token
            log.info(f"[OAuth] JWT会话已从数据库恢复，用户: {union_openid[:8]}...")
            return union_openid
        except jwt.ExpiredSignatureError:
            log.warning(f"[OAuth] JWT已过期")
            self._deactivate_session(token)
            return None
        except jwt.InvalidTokenError as e:
            log.warning(f"[OAuth] JWT验证失败: {e}")
            return None
    
    def revoke_jwt(self, token: str) -> bool:
        """撤销JWT令牌（内存 + 数据库）
        
        Args:
            token: JWT令牌
            
        Returns:
            是否撤销成功
        """
        union_openid = self._jwt_session_cache.pop(token, None)
        if union_openid:
            if self._user_jwt_map.get(union_openid) == token:
                del self._user_jwt_map[union_openid]
            self._deactivate_session(token)
            log.info(f"[OAuth] 已撤销用户 {union_openid[:8]}... 的JWT")
            return True
        # 内存中没有（如重启后缓存丢失），仍尝试从数据库撤销
        row = self._query_session(token)
        if row and row[3]:
            self._deactivate_session(token)
            log.info(f"[OAuth] 已从数据库撤销JWT")
            return True
        return False


# 全局OAuth管理器实例
oauth_manager = OAuthManager()
