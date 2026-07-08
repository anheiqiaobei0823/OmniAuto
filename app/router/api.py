"""Chat API — /v1/chat/completions + /v1/images/generations + /v1/models"""

import time
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.database import db
from app.providers.base import ChatRequest
from app.router_engine.classifier import classify_request
from app.router_engine.dispatcher import dispatch
from app.router_engine.fallback import chat_with_fallback, chat_stream_with_fallback
from app.services.logger import log_call
from app.services.image_store import save_image

router = APIRouter()


async def _get_api_key_id(request: Request) -> int:
    """从请求头中提取 API Key 并查询数据库验证"""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return 0
    key_value = auth[7:].strip()
    if not key_value:
        return 0
    row = await db.fetch_one("SELECT id FROM api_keys WHERE key_value = ? AND is_active = 1", (key_value,))
    return row["id"] if row else 0


async def _get_router_config() -> tuple[str, str, str]:
    """获取路由器配置（硅基流动的 API 地址 + Key + 模型）"""
    router_api_base = await db.get_setting("router_api_base")
    router_api_key = await db.get_setting("router_api_key")
    router_model = await db.get_setting("router_model")

    # 默认值（用户在管理后台设置前使用）
    if not router_api_base:
        router_api_base = "https://api.siliconflow.cn/v1"
    if not router_api_key:
        router_api_key = ""  # 用户必须在后台配置
    if not router_model:
        router_model = "Qwen/Qwen2.5-72B-Instruct"

    return router_api_base, router_api_key, router_model


# ─── /v1/chat/completions ───────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    requested_model = body.get("model", "")
    router_enabled = await db.get_setting("router_enabled")

    # 是否启用路由
    use_router = router_enabled != "0" if router_enabled else True

    # auto / OmniAuto / 空 → 走路由；指定具体模型 → 直接用
    is_auto = requested_model in ("", "auto", "OmniAuto")
    force_model = None if is_auto else requested_model

    if use_router and is_auto:
        # 1. 分类
        router_base, router_key, router_model = await _get_router_config()
        category = await classify_request(messages, router_base, router_key, router_model)
    else:
        category = "默认"

    # 2. 分发
    provider, model_id, provider_name = await dispatch(
        category, messages, stream=stream, force_model=force_model,
    )

    if not provider:
        raise HTTPException(502, "没有可用的模型，请检查 Provider 配置。")

    # 3. 构造内部请求
    chat_req = ChatRequest(
        model=model_id,
        messages=messages,
        stream=stream,
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens"),
        top_p=body.get("top_p"),
        tools=body.get("tools"),
        tool_choice=body.get("tool_choice"),
        response_format=body.get("response_format"),
        extra_body={k: v for k, v in body.items() if k not in (
            "messages", "model", "stream", "temperature", "max_tokens",
            "top_p", "tools", "tool_choice", "response_format",
        )},
    )

    start = time.time()
    key_id = await _get_api_key_id(request)
    if not key_id:
        raise HTTPException(401, "API Key 无效或已禁用")

    if stream:
        return await _handle_stream(chat_req, provider, category, model_id, messages, start, key_id)

    try:
        response = await provider.chat(chat_req)
        elapsed = int((time.time() - start) * 1000)

        await log_call(
            api_key_id=key_id,
            model_used=response.model_used,
            provider_name=response.provider_name,
            category_name=category,
            is_stream=False,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            duration_ms=elapsed,
            success=True,
        )

        return {
            "id": "chatcmpl-omniauto",
            "object": "chat.completion",
            "model": response.model_used,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response.content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        }
    except Exception as e:
        # 主模型失败 → 故障切换
        elapsed = int((time.time() - start) * 1000)
        await log_call(
            api_key_id=key_id,
            model_used=model_id,
            provider_name=provider_name,
            category_name=category,
            is_stream=False,
            duration_ms=elapsed,
            success=False,
            error_msg=str(e),
        )

        if not use_router:
            raise HTTPException(502, f"模型调用失败：{str(e)}")

        fallback_resp = await chat_with_fallback(category, messages, chat_req, model_id)
        elapsed = int((time.time() - start) * 1000)
        await log_call(
            api_key_id=key_id,
            model_used=fallback_resp.model_used,
            provider_name=fallback_resp.provider_name,
            category_name=category,
            is_stream=False,
            prompt_tokens=fallback_resp.prompt_tokens,
            completion_tokens=fallback_resp.completion_tokens,
            total_tokens=fallback_resp.total_tokens,
            duration_ms=elapsed,
            success=True,
        )

        return {
            "id": "chatcmpl-omniauto",
            "object": "chat.completion",
            "model": fallback_resp.model_used or model_id,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": fallback_resp.content}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": fallback_resp.prompt_tokens,
                "completion_tokens": fallback_resp.completion_tokens,
                "total_tokens": fallback_resp.total_tokens,
            },
        }


async def _handle_stream(chat_req, provider, category, model_id, messages, start, key_id=0):
    """处理流式请求"""
    async def generate():
        switched = False
        try:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            async for chunk in provider.chat_stream(chat_req):
                # 检查 chunk 是否是 dict（包含 usage 的最后一块）
                if isinstance(chunk, dict):
                    usage = chunk.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)
                    continue
                yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}, 'index': 0}]})}\n\n"
            yield "data: [DONE]\n\n"
            elapsed = int((time.time() - start) * 1000)
            await log_call(
                api_key_id=key_id,
                model_used=model_id,
                provider_name=provider.config.name,
                category_name=category,
                is_stream=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=elapsed,
                success=True,
            )
            return
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            await log_call(
                api_key_id=key_id,
                model_used=model_id,
                provider_name=provider.config.name,
                category_name=category,
                is_stream=True,
                duration_ms=elapsed,
                success=False,
                error_msg=str(e),
            )
            switched = True

        if not switched:
            return

        # 故障切换流式
        async for chunk in chat_stream_with_fallback(category, messages, chat_req, model_id):
            yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}, 'index': 0}]})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ─── /v1/images/generations ─────────────────────────────

@router.post("/v1/images/generations")
async def images_generations(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    model = body.get("model", "")
    n = body.get("n", 1)
    size = body.get("size", "1024x1024")

    # 生图走生图分类
    provider, model_id, provider_name = await dispatch(
        "生图", [{"role": "user", "content": prompt}], force_model=model
    )

    if not provider:
        raise HTTPException(502, "没有可用的生图模型")

    from app.providers.base import ImageRequest
    img_req = ImageRequest(prompt=prompt, model=model_id, n=n, size=size)

    start = time.time()
    try:
        resp = await provider.image_generate(img_req)
    except Exception as e:
        raise HTTPException(502, f"生图失败：{str(e)}")

    elapsed = int((time.time() - start) * 1000)
    await log_call(
        model_used=resp.model_used,
        provider_name=resp.provider_name,
        category_name="生图",
        is_stream=False,
        duration_ms=elapsed,
        success=True,
    )

    # 保存图片到本地
    local_urls = []
    for url in resp.image_urls:
        try:
            local_url = await save_image(url)
            local_urls.append(local_url)
        except Exception:
            local_urls.append(url)

    return {
        "created": int(time.time()),
        "data": [{"url": url} for url in local_urls],
    }


# ─── /v1/models ─────────────────────────────────────────

@router.get("/v1/models")
async def list_models():
    """对外只暴露 OmniAuto 模型，由路由器自动决定使用哪个实际模型"""
    # 同时用嵌套 + 顶级字段 + modalities 数组，兼容各种第三方客户端
    caps = {
        "supports_text": True,
        "supports_vision": True,
        "supports_image_input": True,
        "supports_image_output": False,
        "supports_tools": True,
        "supports_function_calling": True,
        "supports_reasoning": True,
        "supports_stream": True,
        "supports_image_gen": True,
    }
    return {
        "object": "list",
        "data": [
            {
                "id": "OmniAuto",
                "object": "model",
                "owned_by": "OmniAuto",
                "created": 0,
                "permissions": [],
                # 嵌套格式（部分客户端）
                "capabilities": caps,
                # 顶级布尔格式（另一部分客户端）
                **caps,
                # modalities 数组格式（又一部分客户端）
                "input_modalities": ["text", "image"],
                "output_modalities": ["text", "image"],
            }
        ],
    }
