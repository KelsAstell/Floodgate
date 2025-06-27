import binascii
import json
from fastapi import Response, Request, HTTPException
from starlette.websockets import WebSocket

from config import BOT_SECRET, log, OB_ACCESS_TOKEN

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature


async def _get_ed25519_key(secret: str) -> Ed25519PrivateKey:
    secret = secret.encode()
    seed = secret
    while len(seed) < 32:
        seed += secret
    seed = seed[:32]
    return Ed25519PrivateKey.from_private_bytes(seed)

async def _get_public_key_from_secret(secret: str) -> Ed25519PublicKey:
    private_key = await _get_ed25519_key(secret)
    return private_key.public_key()

# 用于响应平台明文验证请求（含 plain_token）
async def _webhook_verify(payload: dict):
    plain_token = payload.get("plain_token")
    event_ts = payload.get("event_ts")
    try:
        private_key = await _get_ed25519_key(BOT_SECRET)
    except Exception as e:
        log.error(f"Failed to create private key: {e}")
        return Response(content="Failed to create private key", status_code=500)

    msg = f"{event_ts}{plain_token}".encode()
    try:
        signature = private_key.sign(msg)
        signature_hex = binascii.hexlify(signature).decode()
    except Exception as e:
        log.error(f"Failed to sign message: {e}")
        return Response(content="Failed to sign message", status_code=500)

    return Response(
        content=json.dumps({"plain_token": plain_token, "signature": signature_hex}),
        status_code=200
    )

# 用于校验平台事件推送签名是否合法
async def _verify_signature_from_request(request: Request) -> bool:
    try:
        signature_hex = request.headers.get("x-signature-ed25519")
        timestamp = request.headers.get("x-signature-timestamp")
        if not signature_hex or not timestamp:
            log.warning("Missing signature headers")
            return False

        signature = binascii.unhexlify(signature_hex)
        raw_body = await request.body()
        msg = timestamp.encode() + raw_body

        public_key = await _get_public_key_from_secret(BOT_SECRET)
        public_key.verify(signature, msg)  # 会抛出异常表示验证失败
        return True
    except InvalidSignature:
        log.warning("无效的签名")
        return False
    except Exception as e:
        log.error(f"签名校验失败: {e}")
        return False


async def _ob_verify(websocket: WebSocket):
    token = websocket.headers.get("authorization")
    if not token == f"Bearer {OB_ACCESS_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid Signature")


class WebhookVerifier:
    def __init__(self):
        pass

    async def verify_plain_token(self, payload: dict):
        return await _webhook_verify(payload)

    async def verify_onebot_access_token(self,websocket: WebSocket):
        return await _ob_verify(websocket)

    async def verify_signature(self, request: Request):
        return await _verify_signature_from_request(request)


verifier = WebhookVerifier()

