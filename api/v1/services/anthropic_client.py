from functools import lru_cache

from anthropic import AsyncAnthropic

from api.v1.utils.config import config


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
