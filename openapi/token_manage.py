from config import *
import aiohttp
import json
from datetime import datetime, timedelta, timezone
from typing import Optional


class AccessTokenManager:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._expires_in: Optional[datetime] = None
        self.bot_info = type('BotInfo', (), {'id': str(BOT_APPID), 'secret': BOT_SECRET})
        self.auth_base_url = "https://bots.qq.com/app/getAppAccessToken"

    async def get_access_token(self, only_get_token:Optional[bool] = False) -> str:
        if only_get_token:
            return self._access_token
        if (self._access_token is None or
                self._expires_in is None or
                datetime.now(timezone.utc) > self._expires_in - timedelta(seconds=30)):
            await self._refresh_access_token()
            if self._expires_in is not None:
                try:
                    utc8_time = self._expires_in.replace(tzinfo=timezone.utc).astimezone(None)
                    log_message = f"成功刷新了 Access Token，有效时长至：{utc8_time.strftime('%Y-%m-%d %H:%M:%S')}"
                except Exception as e:
                    log_message = f"成功刷新了 Access Token，但格式化时间失败: {e}"
            else:
                log_message = "成功刷新了 Access Token，但过期时间未知"
            log.success(log_message)
        return self._access_token

    async def _refresh_access_token(self):
        payload = {
            "appId": str(BOT_APPID),
            "clientSecret": BOT_SECRET
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    self.auth_base_url,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    raise NetworkError(f"Get authorization failed with status code {response.status}. Please check your config.")
                content = await response.text()
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    raise NetworkError(f"Invalid JSON response: {content}")
                if not isinstance(data, dict) or "access_token" not in data or "expires_in" not in data:
                    raise NetworkError(f"Get authorization failed with invalid response {data}. Please check your config.")
                self._access_token = data["access_token"]
                expires_seconds = int(data["expires_in"])
                self._expires_in = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)

class NetworkError(Exception):
    pass

token_manager = AccessTokenManager()


