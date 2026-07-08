"""Provider 注册中心 — 管理所有 Provider 实例的创建与缓存"""

from typing import Optional
from app.database import db
from app.providers.base import BaseProvider, ProviderConfig
from app.providers.openai_compat import OpenAICompatProvider


class ProviderRegistry:
    """Provider 注册中心 — 按需创建并缓存 Provider 实例"""

    def __init__(self):
        self._cache: dict[int, BaseProvider] = {}

    def _create(self, provider_data: dict) -> BaseProvider:
        """根据数据库记录创建 Provider 实例"""
        config = ProviderConfig(
            id=provider_data["id"],
            name=provider_data["name"],
            api_base=provider_data["api_base"],
            api_path=provider_data.get("api_path") or "/chat/completions",
            api_key=provider_data["api_key"],
        )
        return OpenAICompatProvider(config)

    async def get(self, provider_id: int) -> Optional[BaseProvider]:
        """获取（或创建并缓存）Provider 实例"""
        if provider_id in self._cache:
            return self._cache[provider_id]

        row = await db.get_provider_by_id(provider_id)
        if not row:
            return None

        provider = self._create(row)
        self._cache[provider_id] = provider
        return provider

    async def get_by_model_id(self, model_id: str) -> Optional[tuple[BaseProvider, str]]:
        """根据模型 ID 查找对应的 Provider 和完整 model_id"""
        models = await db.get_all_models()
        for m in models:
            if m["model_id"] == model_id:
                provider = await self.get(m["provider_id"])
                if provider:
                    return provider, m["model_id"]
        return None

    def invalidate(self, provider_id: int):
        """清除缓存（Provider 配置更新后调用）"""
        self._cache.pop(provider_id, None)

    def invalidate_all(self):
        self._cache.clear()


registry = ProviderRegistry()
