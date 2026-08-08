from openai import AsyncOpenAI

from ..agent.state import Event
from ..config import Settings
from .prompts import REPORT_SYSTEM_PROMPT, REPORT_USER_PROMPT


async def generate_report(
    client: AsyncOpenAI, settings: Settings, events: list[Event]
) -> str:
    """调用 LLM 根据事件列表生成本文。"""
    if not events:
        return "今日无记录的工作事件。"

    events_text = "\n".join(
        f"- [{e.type.value}] {e.title}：{e.detail}" for e in events
    )

    response = await client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": REPORT_USER_PROMPT.format(events_text=events_text)},
        ],
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or ""
