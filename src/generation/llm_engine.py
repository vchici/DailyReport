from openai import AsyncOpenAI

from ..agent.state import Event
from ..config import Settings
from .prompts import REPORT_SYSTEM_PROMPT, REPORT_USER_PROMPT


async def generate_report(
    client: AsyncOpenAI,
    settings: Settings,
    events: list[Event],
    related_entries: list[dict] | None = None,
) -> str:
    """调用 LLM 根据事件列表和历史关联记录生成日报。"""
    if not events:
        return "今日无记录的工作事件。"

    events_text = "\n".join(
        f"- [{e.type.value}] {e.title}：{e.detail}" for e in events
    )

    # 格式化历史关联记录
    if related_entries:
        lines = ["\n## 历史相关记录"]
        for i, entry in enumerate(related_entries, 1):
            date = entry.get("date", "未知日期")
            raw = entry.get("raw_input", "")
            ents = ", ".join(entry.get("entities", []))
            lines.append(f"{i}. [{date}] {raw}（标签：{ents}）")
        related_text = "\n".join(lines)
    else:
        related_text = ""

    response = await client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": REPORT_USER_PROMPT.format(
                events_text=events_text,
                related_text=related_text,
            )},
        ],
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or ""
