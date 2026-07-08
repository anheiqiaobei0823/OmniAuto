"""认证模块 — 轻量 JWT + 密码哈希"""

import json
import base64
import hmac
import hashlib
import time
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from app.config import JWT_SECRET

TOKEN_EXPIRE_DAYS = 7


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += '=' * padding
    return base64.urlsafe_b64decode(s.encode('ascii'))


def _hash_password(password: str) -> str:
    """简单密码哈希：sha256(password)"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(_hash_password(password), password_hash)


def create_token(user_id: int, username: str, is_admin: bool) -> str:
    """生成 JWT token，默认 7 天有效"""
    now = int(time.time())
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64encode(json.dumps({
        "sub": user_id,
        "username": username,
        "admin": bool(is_admin),
        "iat": now,
        "exp": now + TOKEN_EXPIRE_DAYS * 86400,
    }).encode())
    signing_input = f"{header}.{payload}"
    signature = _b64encode(hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{signature}"


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """验证并解析 JWT token，过期返回 None"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature_b64 = parts
        payload = json.loads(_b64decode(payload_b64))

        # 验证签名
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = _b64encode(hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature_b64, expected_sig):
            return None

        # 验证过期时间
        if payload.get('exp', 0) < time.time():
            return None

        return payload
    except Exception:
        return None


async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """从请求头中提取并验证 JWT token"""
    auth = request.headers.get('authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    return decode_token(token)


async def require_auth(request: Request) -> Dict[str, Any]:
    """强制要求登录，返回当前用户信息；未登录或 token 无效则抛 401"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "未登录或 token 已过期")
    return user


async def require_admin(request: Request) -> Dict[str, Any]:
    """强制要求管理员权限"""
    user = await require_auth(request)
    if not user.get('admin'):
        raise HTTPException(403, "需要管理员权限")
    return user
