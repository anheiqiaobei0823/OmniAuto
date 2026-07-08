"""管理后台服务 — 提供管理 API 的纯逻辑"""

import re
import secrets
import json
from datetime import datetime
from typing import Optional
from app.database import db


async def verify_admin_password(password: str) -> bool:
    """验证管理密码"""
    from app.config import ADMIN_PASSWORD
    return password == ADMIN_PASSWORD


# ─── 模型能力自动识别（参考 Kelivo 思路） ────────────────

# 视觉关键词
_VISION_PATTERNS = [
    r"vision", r"gpt-4o", r"gpt-4\.1", r"gpt-5", r"claude-3", r"claude-4",
    r"claude-opus", r"claude-sonnet", r"gemini-1\.5", r"gemini-2", r"gemini-3",
    r"qwen-vl", r"qwen2-vl", r"qvq", r"step-1v", r"step-1o",
    r"doubao-seed", r"minicpm-v", r"internvl",
]

# 生图关键词
_IMAGE_GEN_PATTERNS = [
    r"dall-e", r"gpt-image", r"imagen", r"midjourney", r"flux",
    r"seedream", r"seed-diffusion", r"stable-diffusion", r"sdxl",
    r"playground-v2", r"kandinsky", r"qwen-image",
]

# 工具调用关键词（基本所有现代大模型都支持）
_TOOL_PATTERNS = [
    r"gpt-3\.5", r"gpt-4", r"gpt-5", r"claude-3", r"claude-4", r"claude-opus", r"claude-sonnet",
    r"gemini-1", r"gemini-2", r"gemini-3",
    r"deepseek", r"qwen", r"qwen2", r"qwen3",
    r"glm-4", r"chatglm", r"mistral", r"mixtral", r"llama-3", r"llama-3\.1", r"llama-3\.2", r"llama-3\.3",
    r"yi-1\.5", r"yi-large", r"baichuan", r"internlm",
]

# 推理模型关键词
_REASONING_PATTERNS = [
    r"o1", r"o3", r"o4", r"r1", r"reasoning", r"thinking",
    r"qwq", r"deepseek-r", r"deepseek-reasoner", r"gemini-2\.0-thinking",
]


def _match_any(patterns: list, text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def infer_model_capabilities(model_id: str) -> dict:
    """根据模型 ID 推断能力（用于 discover 自动导入时）"""
    mid = (model_id or "").lower()
    return {
        "supports_stream": 1,
        "supports_vision": 1 if _match_any(_VISION_PATTERNS, mid) else 0,
        "supports_tools": 1 if _match_any(_TOOL_PATTERNS, mid) else 0,
        "supports_image_gen": 1 if _match_any(_IMAGE_GEN_PATTERNS, mid) else 0,
        "supports_reasoning": 1 if _match_any(_REASONING_PATTERNS, mid) else 0,
    }


# ─── API Key 管理 ───────────────────────────────────────

def generate_api_key() -> str:
    return "sk-" + secrets.token_hex(24)


async def create_api_key(name: Optional[str] = None, allowed_models: list = None) -> dict:
    key = generate_api_key()
    now = datetime.utcnow().isoformat()
    models_json = json.dumps(allowed_models or [])
    await db.execute(
        "INSERT INTO api_keys (key_value, name, allowed_models, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
        (key, name or "", models_json, now),
    )
    # 返回新 ID
    rows = await db.fetch_all("SELECT MAX(id) as max_id FROM api_keys")
    new_id = rows[0]["max_id"] if rows else 0
    return {
        "id": new_id,
        "key": key,
        "name": name or "",
        "allowed_models": allowed_models or [],
        "created_at": now,
    }


async def list_api_keys() -> list:
    rows = await db.fetch_all(
        "SELECT id, key_value, name, allowed_models, is_active, created_at FROM api_keys ORDER BY created_at DESC"
    )
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["allowed_models"] = json.loads(item.get("allowed_models") or "[]")
        except Exception:
            item["allowed_models"] = []
        result.append(item)
    return result


async def update_api_key(key_id: int, name: str = None, allowed_models: list = None, is_active: bool = None):
    sets = []
    params = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if allowed_models is not None:
        sets.append("allowed_models = ?")
        params.append(json.dumps(allowed_models))
    if is_active is not None:
        sets.append("is_active = ?")
        params.append(1 if is_active else 0)
    if not sets:
        return
    params.append(key_id)
    await db.execute(
        f"UPDATE api_keys SET {', '.join(sets)} WHERE id = ?", tuple(params)
    )


async def toggle_api_key(key_id: int, is_active: bool):
    await db.execute(
        "UPDATE api_keys SET is_active = ? WHERE id = ?", (1 if is_active else 0, key_id)
    )


async def delete_api_key(key_id: int):
    await db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))


# ─── Provider 管理 ──────────────────────────────────────

async def add_provider(name: str, api_base: str, api_key: str, api_path: str = "/chat/completions") -> int:
    now = datetime.utcnow().isoformat()
    await db.execute(
        "INSERT INTO providers (name, api_base, api_path, api_key, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
        (name, api_base, api_path, api_key, now, now),
    )
    rows = await db.fetch_all("SELECT MAX(id) as max_id FROM providers")
    return rows[0]["max_id"] if rows else 0


async def update_provider(pid: int, name: str = None, api_base: str = None, api_path: str = None, api_key: str = None, is_active: bool = None):
    now = datetime.utcnow().isoformat()
    sets = ["updated_at = ?"]
    params: list = [now]
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if api_base is not None:
        sets.append("api_base = ?")
        params.append(api_base)
    if api_path is not None:
        sets.append("api_path = ?")
        params.append(api_path)
    if api_key is not None:
        sets.append("api_key = ?")
        params.append(api_key)
    if is_active is not None:
        sets.append("is_active = ?")
        params.append(1 if is_active else 0)
    params.append(pid)
    await db.execute(
        f"UPDATE providers SET {', '.join(sets)} WHERE id = ?", tuple(params)
    )
    from app.providers.registry import registry
    registry.invalidate(pid)


async def list_providers() -> list:
    return await db.fetch_all("SELECT * FROM providers ORDER BY name")


async def discover_models(api_base: str, api_key: str) -> list:
    """调用 Provider 的 /v1/models 接口获取可用模型"""
    import httpx
    try:
        async with httpx.AsyncClient(
            base_url=api_base.rstrip("/"),
            timeout=15,
            headers={"Authorization": f"Bearer {api_key}"},
        ) as client:
            resp = await client.get("/models")
            resp.raise_for_status()
            data = resp.json()
        return data.get("data", [])
    except Exception as e:
        raise RuntimeError(f"获取模型列表失败：{str(e)}")


async def import_models(provider_id: int, model_list: list[dict]) -> int:
    """将勾选的模型导入数据库，自动识别能力"""
    now = datetime.utcnow().isoformat()
    added = 0
    for m in model_list:
        model_id = m.get("id", "")
        if not model_id:
            continue
        existing = await db.fetch_one(
            "SELECT id FROM models WHERE provider_id = ? AND model_id = ?",
            (provider_id, model_id),
        )
        if existing:
            continue
        caps = infer_model_capabilities(model_id)
        color = await db.get_next_available_color()
        await db.execute(
            """INSERT INTO models (provider_id, model_id, display_name, color,
               supports_stream, supports_vision, supports_tools, supports_image_gen, supports_reasoning,
               is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (provider_id, model_id, m.get("id", ""), color,
             caps["supports_stream"], caps["supports_vision"], caps["supports_tools"],
             caps["supports_image_gen"], caps["supports_reasoning"],
             now, now),
        )
        added += 1
    return added


async def add_single_model(provider_id: int, model_id: str, display_name: str = "",
                            supports_stream: bool = True, supports_vision: bool = False,
                            supports_tools: bool = False, supports_image_gen: bool = False,
                            supports_reasoning: bool = False) -> int:
    """手动添加一个模型（用户自己选能力）"""
    if not model_id:
        raise RuntimeError("模型 ID 不能为空")
    existing = await db.fetch_one(
        "SELECT id FROM models WHERE provider_id = ? AND model_id = ?",
        (provider_id, model_id),
    )
    if existing:
        raise RuntimeError("该模型已存在")
    now = datetime.utcnow().isoformat()
    color = await db.get_next_available_color()
    await db.execute(
        """INSERT INTO models (provider_id, model_id, display_name, color,
           supports_stream, supports_vision, supports_tools, supports_image_gen, supports_reasoning,
           is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (provider_id, model_id, display_name or model_id, color,
         1 if supports_stream else 0, 1 if supports_vision else 0,
         1 if supports_tools else 0, 1 if supports_image_gen else 0,
         1 if supports_reasoning else 0,
         now, now),
    )
    rows = await db.fetch_all("SELECT MAX(id) as max_id FROM models")
    return rows[0]["max_id"] if rows else 0


async def delete_provider(pid: int):
    await db.execute("DELETE FROM providers WHERE id = ?", (pid,))
    await db.execute("DELETE FROM models WHERE provider_id = ?", (pid,))
    await db.execute("DELETE FROM heartbeat_status WHERE provider_id = ?", (pid,))
    await db.execute("DELETE FROM heartbeat_history WHERE provider_id = ?", (pid,))
    from app.providers.registry import registry
    registry.invalidate(pid)


# ─── 分类路由管理 ───────────────────────────────────────

async def list_categories() -> list:
    return await db.fetch_all("SELECT * FROM categories ORDER BY sort_order")


async def add_category(name: str) -> int:
    now = datetime.utcnow().isoformat()
    await db.execute(
        "INSERT INTO categories (name, is_default, sort_order, created_at) VALUES (?, 0, 0, ?)",
        (name, now),
    )
    rows = await db.fetch_all("SELECT MAX(id) as max_id FROM categories")
    return rows[0]["max_id"] if rows else 0


async def delete_category(cat_id: int):
    await db.execute("DELETE FROM categories WHERE id = ? AND is_default = 0", (cat_id,))
    await db.execute("DELETE FROM category_models WHERE category_id = ?", (cat_id,))


async def set_category_models(category_id: int, model_ids: list[int]):
    """设置分类的模型优先级列表（先删后插，按传入顺序排优先级）"""
    await db.execute("DELETE FROM category_models WHERE category_id = ?", (category_id,))
    now = datetime.utcnow().isoformat()
    for i, mid in enumerate(model_ids):
        await db.execute(
            "INSERT INTO category_models (category_id, model_id, priority, created_at) VALUES (?, ?, ?, ?)",
            (category_id, mid, i + 1, now),
        )


async def add_model_to_category(category_id: int, model_id: int):
    """添加一个模型到分类末尾（用于点击"添加"按钮）"""
    existing = await db.fetch_one(
        "SELECT MAX(priority) as max_p FROM category_models WHERE category_id = ?",
        (category_id,),
    )
    next_p = (existing["max_p"] or 0) + 1
    now = datetime.utcnow().isoformat()
    try:
        await db.execute(
            "INSERT INTO category_models (category_id, model_id, priority, created_at) VALUES (?, ?, ?, ?)",
            (category_id, model_id, next_p, now),
        )
    except Exception:
        # 已存在则忽略
        pass


async def remove_model_from_category(category_id: int, model_id: int):
    await db.execute(
        "DELETE FROM category_models WHERE category_id = ? AND model_id = ?",
        (category_id, model_id),
    )


# ─── 模型管理 ───────────────────────────────────────────

async def update_model(model_id: int, **kwargs):
    sets = []
    params = []
    for key, val in kwargs.items():
        sets.append(f"{key} = ?")
        params.append(1 if val is True else (0 if val is False else val))
    if not sets:
        return
    sets.append("updated_at = ?")
    params.append(datetime.utcnow().isoformat())
    params.append(model_id)
    await db.execute(
        f"UPDATE models SET {', '.join(sets)} WHERE id = ?",
        tuple(params),
    )


# ─── 测试连接 ───────────────────────────────────────

async def test_provider_model(provider_id: int, model_id: str) -> tuple[bool, str]:
    """测试某个 provider 下的某个 model 是否能调通"""
    from app.providers.registry import registry
    provider = await registry.get(provider_id)
    if not provider:
        return False, "供应商不存在"
    if not hasattr(provider, "test_chat"):
        return False, "该 Provider 不支持测试"
    return await provider.test_chat(model_id)
