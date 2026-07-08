"""Provider 抽象基类 — 所有 Provider 必须实现此接口"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, Any
from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Provider 配置"""
    id: int
    name: str
    api_base: str
    api_path: str = "/chat/completions"
    api_key: str = ""


@dataclass
class ModelConfig:
    """模型配置"""
    id: int
    model_id: str
    provider_id: int
    supports_stream: bool = True
    supports_vision: bool = False
    supports_tools: bool = False
    supports_image_gen: bool = False


@dataclass
class ChatRequest:
    """统一聊天请求"""
    model: str
    messages: list
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    tools: Optional[list] = None
    tool_choice: Optional[Any] = None
    response_format: Optional[dict] = None
    extra_body: Optional[dict] = None  # 无法映射的额外参数


@dataclass
class ChatResponse:
    """统一聊天响应"""
    content: str
    model_used: str
    provider_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ImageRequest:
    """统一生图请求"""
    prompt: str
    model: str
    n: int = 1
    size: str = "1024x1024"
    negative_prompt: Optional[str] = None


@dataclass
class ImageResponse:
    """统一生图响应"""
    image_urls: list[str]
    model_used: str
    provider_name: str


class BaseProvider(ABC):
    """Provider 基类 — 所有下游供应商插件必须继承此类"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """非流式聊天"""
        ...

    @abstractmethod
    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """流式聊天，逐个 yield 文本块"""
        ...
        yield ""  # pragma: no cover

    @abstractmethod
    async def image_generate(self, request: ImageRequest) -> ImageResponse:
        """图片生成"""
        ...

    @abstractmethod
    async def list_models(self) -> list[dict]:
        """获取可用模型列表（返回模型 ID 列表）"""
        ...

    @abstractmethod
    async def check_health(self) -> tuple[bool, str]:
        """健康检查 → (是否正常, 错误信息)"""
        ...
