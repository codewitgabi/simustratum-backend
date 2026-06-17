from functools import lru_cache

from google import genai

from api.v1.utils.config import config


@lru_cache
def get_gemini_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)
