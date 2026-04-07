import asyncio
from typing import Sequence, List, Type, Any, TypeVar

from langchain.agents import create_agent
from pydantic import BaseModel
from langchain_openai import ChatOpenAI

from app.constants import SupportedModels
from app.settings import get_settings

T = TypeVar('T', bound=BaseModel)


class BaseAgent:
    def __init__(
            self,
            instructions: str,
            model: SupportedModels,
            response_format: Type[BaseModel],
            tools: Sequence[Any] | None = None
    ):
        settings = get_settings()
        llm = ChatOpenAI(
            model=model.value,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            max_retries=3,
            timeout=60.0,
        )
        self._agent = create_agent(
            model=llm,
            tools=tools,
            response_format=response_format,
            system_prompt=instructions,
        )

    def parse(self, messages: List[str]) -> T:
        messages = [{"role": "user", "content": message} for message in messages]
        result = self._agent.invoke({"messages": messages})
        return result["structured_response"]

    async def aparse(self, messages: List[str]) -> T:
        messages = [{"role": "user", "content": message} for message in messages]
        last_exc: BaseException | None = None
        for attempt in range(4):
            try:
                result = await self._agent.ainvoke({"messages": messages})
                return result["structured_response"]
            except BaseException as e:
                last_exc = e
                if attempt == 3:
                    raise
                await asyncio.sleep(min(30.0, 0.5 * (2**attempt)))
        raise last_exc or RuntimeError("aparse failed")
