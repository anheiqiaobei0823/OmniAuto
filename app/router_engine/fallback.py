"""故障切换 — 当主模型失败时按优先级列表重试"""

from typing import Optional, AsyncGenerator
from app.database import db
from app.providers.registry import registry
from app.providers.base import BaseProvider, ChatRequest, ChatResponse


SWITCH_PREFIX = "[已切换到 {} 模型] "


async def chat_with_fallback(
    category_name: str,
    messages: list[dict],
    request: ChatRequest,
    original_model_id: str,
) -> ChatResponse:
    """非流式调用 — 主模型失败后自动切换到优先级列表中的下一个

    Returns:
        ChatResponse 内容中可能包含切换前缀
    """
    categories = await db.get_categories()
    cat_id = None
    for cat in categories:
        if cat["name"] == category_name:
            cat_id = cat["id"]
            break

    if not cat_id:
        cat = await db.get_default_category()
        cat_id = cat["id"] if cat else None

    if not cat_id:
        return ChatResponse(content="没有可用的模型", model_used="", provider_name="", total_tokens=0)

    cat_models = await db.get_category_models(cat_id)
    used_model_ids = set()
    # 先尝试原始模型（可能已经在外面尝试过了，但这里可以再试一次确保）
    # 如果外部已经失败，这里跳过原始模型，直接重试其他
    for cm in cat_models:
        if cm["model_id"] == original_model_id:
            continue
        if cm["model_id"] in used_model_ids:
            continue
        used_model_ids.add(cm["model_id"])

        provider = await registry.get(cm["provider_id"])
        if not provider:
            continue

        try:
            fallback_request = ChatRequest(
                model=cm["model_id"],
                messages=request.messages,
                stream=False,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                tools=request.tools,
                tool_choice=request.tool_choice,
                response_format=request.response_format,
            )
            response = await provider.chat(fallback_request)
            response.content = SWITCH_PREFIX.format(cm["model_id"]) + response.content
            response.model_used = cm["model_id"]
            return response
        except Exception:
            continue

    return ChatResponse(content="所有模型均调用失败，请检查 Provider 配置。", model_used="", provider_name="", total_tokens=0)


async def chat_stream_with_fallback(
    category_name: str,
    messages: list[dict],
    request: ChatRequest,
    original_model_id: str,
) -> AsyncGenerator[str, None]:
    """流式调用 — 主模型失败后自动切换到优先级列表中的下一个"""
    categories = await db.get_categories()
    cat_id = None
    for cat in categories:
        if cat["name"] == category_name:
            cat_id = cat["id"]
            break

    if not cat_id:
        cat = await db.get_default_category()
        cat_id = cat["id"] if cat else None

    if not cat_id:
        yield "没有可用的模型"
        return

    cat_models = await db.get_category_models(cat_id)
    used_model_ids = set()

    for cm in cat_models:
        if cm["model_id"] == original_model_id:
            continue
        if cm["model_id"] in used_model_ids:
            continue
        used_model_ids.add(cm["model_id"])

        provider = await registry.get(cm["provider_id"])
        if not provider:
            continue

        try:
            fallback_request = ChatRequest(
                model=cm["model_id"],
                messages=request.messages,
                stream=True,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                tools=request.tools,
                tool_choice=request.tool_choice,
            )
            yield SWITCH_PREFIX.format(cm["model_id"])
            async for chunk in provider.chat_stream(fallback_request):
                yield chunk
            return
        except Exception:
            continue

    yield "所有模型均调用失败，请检查 Provider 配置。"
