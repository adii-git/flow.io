from ..config import get_settings
from .base import Adapter, AdapterError, AdapterResult, FatalError, RetryableError  # noqa: F401
from .demo import DemoAdapter
from .providers import (AnthropicMessages, BraveSearch, GeminiGenerate, GeminiImages, GroqChat, HuggingFaceChat,
                        LocalStableDiffusion, OpenAIImages, PollinationsImages)

LIVE: dict[str, Adapter] = {
    "anthropic_messages": AnthropicMessages(),
    "brave_search": BraveSearch(),
    "gemini_generate": GeminiGenerate(),
    "gemini_images": GeminiImages(),
    "groq_chat": GroqChat(),
    "huggingface_chat": HuggingFaceChat(),
    "local_stable_diffusion": LocalStableDiffusion(),
    "openai_images": OpenAIImages(),
    "pollinations_images": PollinationsImages(),
}
OVERRIDE: dict[str, Adapter] | None = None  # tests


def get_adapter(adapter_id: str) -> Adapter:
    if OVERRIDE and adapter_id in OVERRIDE:
        return OVERRIDE[adapter_id]
    if get_settings().execution_mode == "demo":
        return DemoAdapter()
    if adapter_id not in LIVE:
        raise FatalError(f"no adapter named {adapter_id} is installed")
    return LIVE[adapter_id]
