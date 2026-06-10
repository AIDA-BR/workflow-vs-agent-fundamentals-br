import os

from agents import OpenAIProvider, RunConfig
from openai import AsyncOpenAI

from src.experiments import Model, is_maritaca_model

_MARITACA_BASE_URL = "https://chat.maritaca.ai/api"


def get_run_config(model: Model) -> RunConfig:
    if is_maritaca_model(model):
        client = AsyncOpenAI(
            base_url=_MARITACA_BASE_URL,
            api_key=os.environ["MARITACA_API_KEY"],
        )
        provider = OpenAIProvider(openai_client=client)
    else:
        provider = OpenAIProvider()
    return RunConfig(model_provider=provider)
