import binascii
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Response
from config import BOT_SECRET,log


async def _get_ed25519_key(secret):
    secret = secret.encode()
    seed = secret
    while len(seed) < 32:
        seed += secret
    seed = seed[:32]
    return Ed25519PrivateKey.from_private_bytes(seed)


async def _webhook_verify(payload):
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
        content=json.dumps({"plain_token": plain_token, "signature": signature_hex}),status_code=200
    )


class WebhookVerifier:
    def __init__(self):
        pass


verifier = WebhookVerifier()
async def webhook_verify(payload):
    return await _webhook_verify(payload)

