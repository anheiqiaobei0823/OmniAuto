"""OpenAI 兼容格式 Provider — 覆盖绝大多数主流 AI API"""

import json
import httpx
from typing import AsyncGenerator
from app.providers.base import (
    BaseProvider, ProviderConfig, ChatRequest, ChatResponse,
    ImageRequest, ImageResponse,
)


class OpenAICompatProvider(BaseProvider):
    """兼容 OpenAI API 格式的 Provider"""

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.config.api_base.rstrip("/"),
            timeout=120,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )

    def _chat_path(self) -> str:
        """聊天接口路径"""
        path = (self.config.api_path or "/chat/completions").strip()
        if not path.startswith("/"):
            path = "/" + path
        return path

    # ─── 聊天（非流式） ──────────────────────────────────

    async def chat(self, request: ChatRequest) -> ChatResponse:
        body = self._build_chat_body(request, stream=False)
        async with self._client() as client:
            resp = await client.post(self._chat_path(), json=body)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})

        return ChatResponse(
            content=content or "",
            model_used=data.get("model", request.model),
            provider_name=self.config.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    # ─── 聊天（流式） ────────────────────────────────────

    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        body = self._build_chat_body(request, stream=True)
        # 请求返回 usage 信息
        body.setdefault("stream_options", {}).setdefault("include_usage", True)
        async with self._client() as client:
            async with client.stream("POST", self._chat_path(), json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        # 提取 usage（通常在最后一个 chunk）
                        usage = chunk.get("usage")
                        if usage:
                            yield {"usage": usage}
                            continue
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    # ─── 图片生成 ────────────────────────────────────────

    async def image_generate(self, request: ImageRequest) -> ImageResponse:
        body = {
            "model": request.model,
            "prompt": request.prompt,
            "n": request.n,
            "size": request.size,
        }
        if request.negative_prompt:
            body["negative_prompt"] = request.negative_prompt

        async with self._client() as client:
            resp = await client.post("/images/generations", json=body)
            resp.raise_for_status()
            data = resp.json()

        urls = [item["url"] for item in data.get("data", [])]
        return ImageResponse(
            image_urls=urls,
            model_used=data.get("model", request.model),
            provider_name=self.config.name,
        )

    # ─── 获取模型列表 ────────────────────────────────────

    async def list_models(self) -> list[dict]:
        async with self._client() as client:
            resp = await client.get("/models")
            resp.raise_for_status()
            data = resp.json()
        return data.get("data", [])

    # ─── 健康检查 ────────────────────────────────────────

    async def check_health(self) -> tuple[bool, str]:
        try:
            async with self._client() as client:
                resp = await client.get("/models", timeout=10)
                return True, ""
        except Exception as e:
            return False, str(e)

    # ─── 实际聊天测试（连通性 + 响应能力） ──────────────

    async def test_chat(self, model_id: str) -> tuple[bool, str]:
        """用最小请求测试模型是否可调通"""
        body = {
            "model": model_id,
            "messages": [{"role": "user", "content": "你好，请简短回复"}],
            "max_tokens": 50,
        }
        try:
            async with self._client() as client:
                resp = await client.post(self._chat_path(), json=body, timeout=20)
                if resp.status_code >= 400:
                    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
                data = resp.json()
            message = data.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "")
            reasoning = message.get("reasoning_content", "")
            if content:
                return True, f"成功：{content[:30]}"
            if reasoning:
                return True, f"成功：{reasoning[:30]}"
            return True, "成功：模型未返回文本内容"
        except Exception as e:
            return False, str(e)[:200]

    # ─── 构建请求体 ──────────────────────────────────────

    def _build_chat_body(self, request: ChatRequest, stream: bool) -> dict:
        body = {
            "model": request.model,
            "messages": request.messages,
            "stream": stream,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.tools is not None:
            body["tools"] = request.tools
        if request.tool_choice is not None:
            body["tool_choice"] = request.tool_choice
        if request.response_format is not None:
            body["response_format"] = request.response_format
        if request.extra_body is not None:
            body.update(request.extra_body)
        return body
