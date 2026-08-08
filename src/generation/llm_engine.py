from openai import AsyncOpenAI

from ..config import Settings
from .prompts import (
    PLAN_SYSTEM_PROMPT,
    PLAN_USER_PROMPT,
    REPORT_SYSTEM_PROMPT,
    REPORT_USER_PROMPT,
)


async def generate_report(
    client: AsyncOpenAI,
    settings: Settings,
    entries: list[dict],
    related_entries: list[dict] | None = None,
) -> str:
    """调用 LLM 根据当日全部条目（含待办和已完成）生成日报。"""
    if not entries:
        return "今日无记录。"

    # 按 status 分组格式化
    todo_lines: list[str] = []
    done_lines: list[str] = []
    for entry in entries:
        status = entry.get("status", "done")
        raw = entry.get("raw_input", "")
        if status == "todo":
            todo_lines.append(f"- [待办] {raw}")
        else:
            done_lines.append(f"- [已完成] {raw}")

    parts: list[str] = []
    if done_lines:
        parts.append("### 已完成\n" + "\n".join(done_lines))
    if todo_lines:
        parts.append("### 待办\n" + "\n".join(todo_lines))
    entries_text = "\n\n".join(parts) if parts else "今日无记录。"

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
                entries_text=entries_text,
                related_text=related_text,
            )},
        ],
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or ""


async def generate_suggestion(
    client: AsyncOpenAI,
    settings: Settings,
    raw_input: str,
    entities: list[str],
    related_entries: list[dict],
) -> str:
    """针对用户计划，基于历史记录生成建议方案。"""
    # 格式化历史关联记录
    if related_entries:
        lines = []
        for i, entry in enumerate(related_entries, 1):
            date = entry.get("date", "未知日期")
            raw = entry.get("raw_input", "")
            lines.append(f"{i}. [{date}] {raw}")
        related_text = "\n".join(lines)
    else:
        related_text = "无相关历史记录。"

    response = await client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": PLAN_USER_PROMPT.format(
                raw_input=raw_input,
                entities=", ".join(entities) if entities else "无",
                related_text=related_text,
            )},
        ],
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or ""
