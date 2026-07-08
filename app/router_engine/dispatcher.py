"""分发器 — 根据分类和优先级列表选择最佳模型"""

from typing import Optional
from app.database import db
from app.providers.registry import registry
from app.providers.base import BaseProvider


async def dispatch(
    category_name: str,
    messages: list[dict],
    stream: bool = False,
    force_model: Optional[str] = None,
) -> tuple[Optional[BaseProvider], Optional[str], Optional[str]]:
    """根据分类分发请求到对应的模型

    Args:
        category_name: 分类名称
        messages: 请求消息（用于检查是否带图）
        stream: 是否流式
        force_model: 强制指定模型 ID（跳过路由）

    Returns:
        (provider, model_id, provider_name) 或 (None, None, None)
    """
    # 检查是否需要 vision 能力
    needs_vision = _has_image(messages)

    # 优先手动指定模型
    if force_model:
        result = await registry.get_by_model_id(force_model)
        if result:
            provider, model_id = result
            return provider, model_id, provider.config.name
        return None, None, None

    # 按分类查优先级列表
    categories = await db.get_categories()
    target_cat = None
    for cat in categories:
        if cat["name"] == category_name:
            target_cat = cat
            break

    if not target_cat:
        # 掉落到默认分类
        target_cat = await db.get_default_category()

    if not target_cat:
        return None, None, None

    # 获取该分类的模型优先级列表
    cat_models = await db.get_category_models(target_cat["id"])

    for cm in cat_models:
        # 过滤 vision 需求
        if needs_vision and not cm["supports_vision"]:
            continue

        # 流式过滤
        if stream and not cm["supports_stream"]:
            continue

        # 尝试创建并缓存 provider
        provider = await registry.get(cm["provider_id"])
        if not provider:
            continue

        return provider, cm["model_id"], cm["provider_name"]

    return None, None, None


def _has_image(messages: list[dict]) -> bool:
    """检查消息中是否包含图片"""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False
