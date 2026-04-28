from __future__ import annotations
import base64
import os
import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings


def hash_password(password: str) -> str:
    peppered = password + settings.pepper
    return bcrypt.hashpw(peppered.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    peppered = password + settings.pepper
    return bcrypt.checkpw(peppered.encode(), hashed.encode())


def _key() -> bytes:
    return base64.b64decode(settings.encryption_key)


def encrypt(plaintext: str) -> str:
    key = _key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # nonce(12) + tag(16) + ciphertext — tag is appended by AESGCM
    return base64.b64encode(nonce + ct).decode()


def decrypt(blob: str) -> str:
    key = _key()
    raw = base64.b64decode(blob)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()


def mask_key(key: str) -> str:
    if len(key) < 8:
        return "****"
    return key[:3] + "..." + key[-4:]
