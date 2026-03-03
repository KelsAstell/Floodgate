import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple

import jwt
from cachetools import TTLCache

from config import BOT_SECRET, OAUTH_LOGIN_TOKEN_TTL, OAUTH_JWT_EXPIRY_DAYS, OAUTH_LOGIN_TOKEN_LENGTH, log


class OAuthManager:
    """OAuth 登录管理器，处理令牌生成、JWT签发和验证"""
    
    def __init__(self):
        # 登录令牌缓存 (TTL=5分钟)
        self._login_token_cache: TTLCache = TTLCache(
            maxsize=1000, 
            ttl=OAUTH_LOGIN_TOKEN_TTL
        )
        # JWT会话缓存 (TTL=15天)
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
    
    def verify_login_token(self, token: str) -> Optional[str]:
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
    
    def create_jwt(self, union_openid: str) -> Tuple[str, int]:
        """创建JWT令牌，同时使该用户的旧JWT失效
        
        Args:
            union_openid: 用户的union_openid
            
        Returns:
            (jwt_token, expires_in_seconds)
        """
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
        
        # 存储JWT会话
        self._jwt_session_cache[jwt_token] = union_openid
        self._user_jwt_map[union_openid] = jwt_token
        
        log.info(f"[OAuth] 为用户 {union_openid[:8]}... 签发JWT，有效期{OAUTH_JWT_EXPIRY_DAYS}天")
        return jwt_token, expires_in
    
    def verify_jwt(self, token: str) -> Optional[str]:
        """验证JWT令牌
        
        Args:
            token: JWT令牌
            
        Returns:
            验证成功返回union_openid，失败返回None
        """
        # 先检查是否在会话缓存中（处理已被撤销的情况）
        if token not in self._jwt_session_cache:
            log.warning(f"[OAuth] JWT不在会话缓存中（可能已被撤销或过期）")
            return None
        
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            union_openid = payload.get("union_openid")
            if union_openid:
                return union_openid
            log.warning(f"[OAuth] JWT payload中缺少union_openid")
            return None
        except jwt.ExpiredSignatureError:
            log.warning(f"[OAuth] JWT已过期")
            # 清理过期的JWT
            self._jwt_session_cache.pop(token, None)
            return None
        except jwt.InvalidTokenError as e:
            log.warning(f"[OAuth] JWT验证失败: {e}")
            return None
    
    def revoke_jwt(self, token: str) -> bool:
        """撤销JWT令牌
        
        Args:
            token: JWT令牌
            
        Returns:
            是否撤销成功
        """
        union_openid = self._jwt_session_cache.pop(token, None)
        if union_openid:
            if self._user_jwt_map.get(union_openid) == token:
                del self._user_jwt_map[union_openid]
            log.info(f"[OAuth] 已撤销用户 {union_openid[:8]}... 的JWT")
            return True
        return False


# 全局OAuth管理器实例
oauth_manager = OAuthManager()
