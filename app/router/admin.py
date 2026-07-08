"""管理后台 API — /admin/*"""

import json
from datetime import datetime
import hashlib
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from pathlib import Path
from app.database import db
from app.services import admin_service
from app.services.auth import require_auth, require_admin, get_current_user, create_token, verify_password, _hash_password
from app.services.logger import get_logs, get_token_stats, get_token_stats_by_hour, get_token_stats_by_range
from app.config import REQUIRE_AUTH

router = APIRouter(prefix="/OmniAuto")


async def safe_json_body(request: Request) -> dict:
    try:
        return await request.json()
    except (json.JSONDecodeError, ValueError):
        return {}


async def verify_auth(request: Request):
    """要求登录（不要求管理员），REQUIRE_AUTH 关闭时直接放行"""
    if REQUIRE_AUTH:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(401, "未登录或 token 已过期")
        request.state.user_id = user["sub"]
        request.state.username = user["username"]
        request.state.is_admin = user.get("admin", False)
    return request


async def verify_admin(request: Request):
    """要求管理员登录"""
    if REQUIRE_AUTH:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(401, "未登录或 token 已过期")
        if not user.get("admin"):
            raise HTTPException(403, "需要管理员权限")
        request.state.user_id = user["sub"]
        request.state.username = user["username"]
        request.state.is_admin = True
    return request


def _uid(request: Request) -> int:
    """从 request.state 取 user_id，未认证时返回 0"""
    return int(getattr(request.state, "user_id", 0))


# ─── 管理后台首页 ───────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_index():
    html_path = Path(__file__).parent.parent / "admin" / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(
            html_path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
        )
    return HTMLResponse("<h1>OmniAuto 管理后台</h1><p>请先构建前端页面。</p>")


# ─── 认证 ──────────────────────────────────────────────

@router.post("/auth/login")
async def admin_login(request: Request):
    body = await safe_json_body(request)
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(400, "用户名和密码不能为空")
    row = await db.fetch_one(
        "SELECT id, username, password_hash, is_admin FROM users WHERE username = ? AND is_active = 1",
        (username,)
    )
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")
    token = create_token(row["id"], row["username"], row["is_admin"])
    return {"ok": True, "token": token, "username": row["username"], "is_admin": bool(row["is_admin"])}


@router.post("/auth/register")
async def admin_register(request: Request):
    """用户注册（需管理员开启 allow_registration）"""
    body = await safe_json_body(request)
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(400, "用户名和密码不能为空")
    if len(username) < 2 or len(username) > 20:
        raise HTTPException(400, "用户名长度 2-20 位")
    if not username.replace("_", "").isalnum():
        raise HTTPException(400, "用户名只能包含字母、数字、下划线")

    allow = await db.get_setting("allow_registration")
    if allow != "1":
        raise HTTPException(403, "当前未开放注册")

    now = datetime.now().isoformat()
    try:
        await db.execute(
            "INSERT INTO users (username, password_hash, is_admin, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, _hash_password(password), 0, 1, now, now)
        )
    except Exception:
        raise HTTPException(400, "用户名已存在")
    return {"ok": True}


@router.get("/auth/me")
async def me(user=Depends(require_auth)):
    return {"ok": True, "username": user["username"], "is_admin": user["admin"]}


@router.put("/auth/password")
async def change_my_password(request: Request, user=Depends(require_auth)):
    """当前登录用户修改自己的密码"""
    body = await safe_json_body(request)
    old_pwd = body.get("old_password", "")
    new_pwd = body.get("new_password", "")
    if not old_pwd or not new_pwd:
        raise HTTPException(400, "旧密码和新密码不能为空")
    row = await db.fetch_one("SELECT password_hash FROM users WHERE id = ?", (user["sub"],))
    if not row or not verify_password(old_pwd, row["password_hash"]):
        raise HTTPException(401, "旧密码错误")
    await db.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (_hash_password(new_pwd), datetime.now().isoformat(), user["sub"])
    )
    return {"ok": True}


# ─── 用户管理（仅管理员） ───────────────────────────────

@router.get("/users")
async def list_users(request: Request = Depends(verify_admin)):
    rows = await db.fetch_all(
        "SELECT id, username, is_admin, is_active, created_at FROM users ORDER BY id"
    )
    return [{**r, "is_admin": bool(r["is_admin"]), "is_active": bool(r["is_active"])} for r in rows]


@router.post("/users")
async def create_user(request: Request = Depends(verify_admin)):
    body = await safe_json_body(request)
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(400, "用户名和密码不能为空")
    now = datetime.now().isoformat()
    try:
        await db.execute(
            "INSERT INTO users (username, password_hash, is_admin, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, _hash_password(password), 0, 1, now, now)
        )
    except Exception:
        raise HTTPException(400, "用户名已存在")
    return {"ok": True}


@router.delete("/users/{uid}")
async def delete_user(uid: int, request: Request = Depends(verify_admin)):
    """删除用户，但禁止删除 admin 账号"""
    row = await db.fetch_one("SELECT username FROM users WHERE id = ?", (uid,))
    if not row:
        raise HTTPException(404, "用户不存在")
    if row["username"] == "admin":
        raise HTTPException(403, "不能删除 admin 账号")
    await db.execute("DELETE FROM users WHERE id = ?", (uid,))
    return {"ok": True}


@router.put("/users/{uid}/password")
async def reset_user_password(uid: int, request: Request = Depends(verify_admin)):
    """管理员重置指定用户的密码"""
    body = await safe_json_body(request)
    new_pwd = body.get("password", "")
    if not new_pwd:
        raise HTTPException(400, "密码不能为空")
    await db.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (_hash_password(new_pwd), datetime.now().isoformat(), uid)
    )
    return {"ok": True}


# ══════════════════════════════════════════════════════════
# 以下为所有用户（登录即可）可操作的接口
# ══════════════════════════════════════════════════════════

# ─── API Key 管理 ────────────────────────────────────────

@router.get("/api-keys")
async def list_keys(request: Request = Depends(verify_auth)):
    return await admin_service.list_api_keys(user_id=_uid(request))


@router.post("/api-keys")
async def create_key(request: Request = Depends(verify_auth)):
    body = await safe_json_body(request)
    result = await admin_service.create_api_key(
        name=body.get("name", ""),
        allowed_models=body.get("allowed_models", []),
        user_id=_uid(request),
    )
    return {"ok": True, "data": result}


@router.put("/api-keys/{key_id}")
async def update_key(key_id: int, request: Request = Depends(verify_auth)):
    body = await safe_json_body(request)
    await admin_service.update_api_key(
        key_id,
        name=body.get("name"),
        allowed_models=body.get("allowed_models"),
        is_active=body.get("is_active"),
    )
    return {"ok": True}


@router.delete("/api-keys/{key_id}")
async def delete_key(key_id: int, request: Request = Depends(verify_auth)):
    await admin_service.delete_api_key(key_id)
    return {"ok": True}


# ─── Provider 管理 ──────────────────────────────────────

@router.get("/providers")
async def list_providers(request: Request = Depends(verify_auth)):
    providers = await admin_service.list_providers(user_id=_uid(request))
    result = []
    for p in providers:
        models = await db.get_models_by_provider(p["id"])
        result.append({**p, "models": models})
    return result


@router.post("/providers")
async def add_provider(request: Request = Depends(verify_auth)):
    body = await safe_json_body(request)
    pid = await admin_service.add_provider(
        name=body["name"],
        api_base=body["api_base"],
        api_key=body["api_key"],
        api_path=body.get("api_path", "/chat/completions"),
        user_id=_uid(request),
    )
    return {"ok": True, "id": pid}


@router.put("/providers/{pid}")
async def update_provider(pid: int, request: Request = Depends(verify_auth)):
    body = await safe_json_body(request)
    await admin_service.update_provider(
        pid,
        name=body.get("name"),
        api_base=body.get("api_base"),
        api_path=body.get("api_path"),
        api_key=body.get("api_key"),
        is_active=body.get("is_active"),
    )
    return {"ok": True}


@router.delete("/providers/{pid}")
async def delete_provider(pid: int, request: Request = Depends(verify_auth)):
    await admin_service.delete_provider(pid)
    return {"ok": True}


# ─── 模型发现 ───────────────────────────────────────────

@router.post("/providers/{pid}/discover")
async def discover_models(pid: int, request: Request = Depends(verify_auth)):
    """只拉取模型列表，不导入"""
    provider = await db.get_provider_by_id(pid)
    if not provider:
        raise HTTPException(404, "Provider 不存在")
    try:
        models = await admin_service.discover_models(provider["api_base"], provider["api_key"])
        return {"ok": True, "models": models}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/providers/{pid}/import-models")
async def import_models(pid: int, request: Request = Depends(verify_auth)):
    """导入勾选的模型"""
    body = await safe_json_body(request)
    added = await admin_service.import_models(pid, body.get("models", []))
    return {"ok": True, "added": added}


# ─── 模型管理 ───────────────────────────────────────────

@router.get("/models")
async def list_models(request: Request = Depends(verify_auth)):
    return await db.get_all_models()


@router.put("/models/{mid}")
async def update_model(mid: int, request: Request = Depends(verify_auth)):
    body = await safe_json_body(request)
    await admin_service.update_model(mid, **body)
    return {"ok": True}


@router.delete("/models/{mid}")
async def delete_model(mid: int, request: Request = Depends(verify_auth)):
    await db.execute("DELETE FROM models WHERE id = ?", (mid,))
    await db.execute("DELETE FROM category_models WHERE model_id = ?", (mid,))
    return {"ok": True}


@router.post("/providers/{pid}/add-model")
async def add_single_model(pid: int, request: Request = Depends(verify_auth)):
    """手动添加单个模型（用户自己选能力）"""
    body = await safe_json_body(request)
    try:
        mid = await admin_service.add_single_model(
            provider_id=pid,
            model_id=body.get("model_id", "").strip(),
            display_name=body.get("display_name", "").strip(),
            supports_stream=bool(body.get("supports_stream", True)),
            supports_vision=bool(body.get("supports_vision", False)),
            supports_tools=bool(body.get("supports_tools", False)),
            supports_image_gen=bool(body.get("supports_image_gen", False)),
            supports_reasoning=bool(body.get("supports_reasoning", False)),
        )
        return {"ok": True, "id": mid}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/models/{mid}/test")
async def test_model(mid: int, request: Request = Depends(verify_auth)):
    """测试某个模型是否可调通"""
    model = await db.fetch_one("SELECT * FROM models WHERE id = ?", (mid,))
    if not model:
        raise HTTPException(404, "模型不存在")
    ok, msg = await admin_service.test_provider_model(model["provider_id"], model["model_id"])
    return {"ok": ok, "message": msg}


# ─── 分类路由管理 ───────────────────────────────────────

@router.get("/categories")
async def list_categories(request: Request = Depends(verify_auth)):
    uid = _uid(request)
    if uid:
        await db.ensure_user_categories(uid)
    cats = await admin_service.list_categories(user_id=uid)
    result = []
    for cat in cats:
        models = await db.get_category_models(cat["id"])
        result.append({
            "id": cat["id"],
            "name": cat["name"],
            "is_default": cat["is_default"],
            "sort_order": cat["sort_order"],
            "models": [{"id": m["id"], "model_id": m["model_id"], "priority": m["priority"], "provider_name": m["provider_name"]} for m in models],
        })
    return result


@router.post("/categories")
async def add_category(request: Request = Depends(verify_auth)):
    body = await safe_json_body(request)
    cid = await admin_service.add_category(body["name"], user_id=_uid(request))
    return {"ok": True, "id": cid}


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int, request: Request = Depends(verify_auth)):
    await admin_service.delete_category(cat_id)
    return {"ok": True}


@router.put("/categories/{cat_id}/models")
async def set_category_models(cat_id: int, request: Request = Depends(verify_auth)):
    body = await safe_json_body(request)
    await admin_service.set_category_models(cat_id, body.get("model_ids", []))
    return {"ok": True}


@router.post("/categories/{cat_id}/models/{model_id}")
async def add_cat_model(cat_id: int, model_id: int, request: Request = Depends(verify_auth)):
    """添加单个模型到分类末尾"""
    await admin_service.add_model_to_category(cat_id, model_id)
    return {"ok": True}


@router.delete("/categories/{cat_id}/models/{model_id}")
async def remove_cat_model(cat_id: int, model_id: int, request: Request = Depends(verify_auth)):
    await admin_service.remove_model_from_category(cat_id, model_id)
    return {"ok": True}


# ─── 日志/用量 ───────────────────────────────────────────

@router.get("/logs")
async def list_logs(request: Request = Depends(verify_auth)):
    """调用记录，支持分页和日期过滤"""
    limit = int(request.query_params.get("limit", 100))
    offset = int(request.query_params.get("offset", 0))
    return await get_logs(user_id=_uid(request), limit=limit, offset=offset)


@router.get("/logs/stats")
async def token_stats(request: Request = Depends(verify_auth)):
    return await get_token_stats(user_id=_uid(request))


@router.get("/logs/hourly")
async def token_stats_hourly(request: Request = Depends(verify_auth)):
    """按小时统计今日 token 用量"""
    return await get_token_stats_by_hour(user_id=_uid(request))


@router.get("/logs/range")
async def token_stats_range(request: Request, request_dep=Depends(verify_auth)):
    """按日期范围统计 token 用量"""
    range_key = request.query_params.get("range", "today")
    return await get_token_stats_by_range(range_key, user_id=_uid(request))


# ─── 心跳状态 ───────────────────────────────────────────

@router.get("/heartbeat")
async def heartbeat_status(request: Request = Depends(verify_auth)):
    uid = _uid(request)
    return await db.fetch_all(
        """SELECT hs.* FROM heartbeat_status hs
           JOIN providers p ON hs.provider_id = p.id
           WHERE ? = 0 OR p.user_id = ?""",
        (uid, uid),
    )


@router.get("/heartbeat/history")
async def heartbeat_history(request: Request = Depends(verify_auth)):
    """用户 Provider 最近 10 次心跳历史"""
    uid = _uid(request)
    rows = await db.fetch_all(
        """SELECT hh.*, p.name as provider_name
           FROM heartbeat_history hh
           JOIN providers p ON hh.provider_id = p.id
           WHERE hh.id IN (
             SELECT id FROM heartbeat_history hh2
             WHERE hh2.provider_id = hh.provider_id
             ORDER BY created_at DESC LIMIT 10
           ) AND (? = 0 OR p.user_id = ?)
           ORDER BY hh.provider_id, hh.created_at DESC""",
        (uid, uid),
    )
    return rows


@router.post("/heartbeat/refresh")
async def heartbeat_refresh(request: Request = Depends(verify_auth)):
    """手动触发心跳检测"""
    from app.services.heartbeat import heartbeat_all
    await heartbeat_all()
    return {"ok": True}


# ─── 系统设置（仅管理员） ───────────────────────────────

@router.get("/settings")
async def get_settings(request: Request = Depends(verify_auth)):
    settings = await db.fetch_all("SELECT * FROM settings")
    return {s["key"]: s["value"] for s in settings}


@router.put("/settings")
async def update_settings(request: Request = Depends(verify_admin)):
    body = await safe_json_body(request)
    for key, value in body.items():
        await db.set_setting(key, str(value))
    return {"ok": True}


@router.post("/router/test")
async def test_router(request: Request = Depends(verify_auth)):
    """测试智能路由模型是否可调通"""
    import httpx
    body = await safe_json_body(request)
    api_base = (body.get("api_base") or "").rstrip("/")
    api_key = body.get("api_key") or ""
    model = body.get("model") or ""
    if not api_base or not api_key or not model:
        raise HTTPException(400, "缺少 api_base / api_key / model")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{api_base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            )
        if resp.status_code >= 400:
            return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "message": f"成功：{content[:30]}"}
    except Exception as e:
        return {"ok": False, "message": str(e)[:200]}


@router.post("/clear-all")
async def clear_all_data(request: Request = Depends(verify_auth)):
    """清除当前用户的所有业务数据"""
    uid = _uid(request)
    # 删除当前用户的模型
    await db.execute("""
        DELETE FROM models WHERE provider_id IN
        (SELECT id FROM providers WHERE user_id = ?)
    """, (uid,))
    await db.execute("DELETE FROM heartbeat_status WHERE provider_id IN (SELECT id FROM providers WHERE user_id = ?)", (uid,))
    await db.execute("DELETE FROM heartbeat_history WHERE provider_id IN (SELECT id FROM providers WHERE user_id = ?)", (uid,))
    await db.execute("DELETE FROM category_models WHERE category_id IN (SELECT id FROM categories WHERE user_id = ?)", (uid,))
    for table in ["providers", "api_keys", "categories"]:
        await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
    if uid:
        await db.ensure_user_categories(uid)
    return {"ok": True}


@router.get("/public-config")
async def public_config():
    """返回公开配置（前端登录页用）"""
    from app.config import REQUIRE_AUTH
    allow_reg = await db.get_setting("allow_registration")
    return {"require_auth": REQUIRE_AUTH, "allow_registration": allow_reg == "1"}
