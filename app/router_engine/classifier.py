"""智能分类器 — 通过硅基流动免费模型判断请求属于哪个分类"""

import json
from typing import Optional
import httpx
from app.database import db
from app.config import DEFAULT_ROUTER_MODEL


# ─── 分类 Prompt ────────────────────────────────────────

CLASSIFIER_SYSTEM_PROMPT = """你是一个 AI 请求分类器。你的任务是将用户的输入归类到以下分类之一：
- 聊天：日常对话、闲聊、问答、解释概念
- 写代码：编程、调试、技术问题、代码审查
- 写作：文案、文章、翻译、润色、创作
- 生图：图片生成、绘画、图像相关（注意：文字请求也可能需要生图）
- 长任务：复杂推理、多步骤分析、架构设计、长文生成、报告

规则：
1. 只返回分类名称，不要任何其他文字。
2. 如果有图片信息（比如用户上传了截图），归类为"生图"。
3. 如果涉及大量代码或技术实现，归类为"写代码"。
4. 如果不确定，返回"默认"。
5. 如果生成了图片 prompt 类的，归类为"生图"。
"""


async def classify_request(
    messages: list[dict],
    router_api_base: str,
    router_api_key: str,
    router_model: Optional[str] = None,
) -> str:
    """调用路由器模型判断请求分类

    Args:
        messages: 原始请求消息列表
        router_api_base: 硅基流动 API 地址
        router_api_key: 硅基流动 API Key
        router_model: 路由器模型 ID，默认使用 GLM-4-9B-Chat

    Returns:
        分类名称（聊天/写代码/写作/生图/长任务/默认）
    """
    model = router_model or DEFAULT_ROUTER_MODEL

    # 先检查是否有图片消息 → 直接生图
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return "生图"

    # 提取用户最后一条消息用于分类
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            last_user_msg = content[:500] if isinstance(content, str) else str(content)
            break

    if not last_user_msg.strip():
        return "默认"

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": f"请分类下面的输入：\n{last_user_msg}"},
        ],
        "temperature": 0.1,  # 低温度让判断更稳定
        "max_tokens": 20,
    }

    try:
        async with httpx.AsyncClient(
            base_url=router_api_base.rstrip("/"),
            timeout=15,
            headers={
                "Authorization": f"Bearer {router_api_key}",
                "Content-Type": "application/json",
            },
        ) as client:
            resp = await client.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()

        category = data["choices"][0]["message"]["content"].strip()
        valid = {"聊天", "写代码", "写作", "生图", "长任务", "默认"}
        return category if category in valid else "默认"
    except Exception:
        return "默认"
