from openai import AsyncOpenAI

from ..config import Settings
from .prompts import (
    CHAT_SYSTEM_PROMPT,
    CHAT_USER_PROMPT,
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

    # 提取结构化匹配对：done 条目中已记录的 matched_todos
    matched_parts: list[str] = []
    for entry in entries:
        if entry.get("status") == "done" and entry.get("matched_todos"):
            done_text = entry["raw_input"]
            for todo_text in entry["matched_todos"]:
                matched_parts.append(f"- 「{done_text}」✅ 对应待办「{todo_text}」")
    matched_text = "\n".join(matched_parts) if matched_parts else ""

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
                matched_text=matched_text,
                related_text=related_text,
            )},
        ],
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or ""


async def chat_response(
    client: AsyncOpenAI,
    settings: Settings,
    user_query: str,
    related_entries: list[dict],
    web_results: list[dict] | None = None,
    history: list[dict] | None = None,
) -> str:
    """自由对话，结合本地历史、联网搜索和多轮对话上下文回答用户问题。

    history 为之前的对话记录（user/assistant 交替），用于多轮记忆。
    """
    # 格式化本地历史
    if related_entries:
        lines = []
        for i, entry in enumerate(related_entries, 1):
            date = entry.get("date", "未知日期")
            raw = entry.get("raw_input", "")
            lines.append(f"{i}. [{date}] {raw}")
        related_text = "\n".join(lines)
    else:
        related_text = "无相关历史记录。"

    # 格式化联网搜索
    if web_results:
        lines = []
        for i, r in enumerate(web_results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   {r['url']}")
        web_text = "\n".join(lines)
    else:
        web_text = "无联网搜索结果。"

    messages: list[dict] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({
        "role": "user",
        "content": CHAT_USER_PROMPT.format(
            user_query=user_query,
            related_text=related_text,
            web_text=web_text,
        ),
    })

    response = await client.chat.completions.create(
        model=settings.model_name,
        messages=messages,
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or ""


async def generate_suggestion(
    client: AsyncOpenAI,
    settings: Settings,
    raw_input: str,
    entities: list[str],
    related_entries: list[dict],
    web_results: list[dict] | None = None,
) -> str:
    """针对用户计划，结合本地历史和联网搜索生成建议方案。"""
    # 格式化本地历史关联记录
    if related_entries:
        lines = []
        for i, entry in enumerate(related_entries, 1):
            date = entry.get("date", "未知日期")
            raw = entry.get("raw_input", "")
            lines.append(f"{i}. [{date}] {raw}")
        related_text = "\n".join(lines)
    else:
        related_text = "无相关历史记录。"

    # 格式化联网搜索结果
    if web_results:
        lines = []
        for i, r in enumerate(web_results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   {r['url']}")
        web_text = "\n".join(lines)
    else:
        web_text = "无联网搜索结果。"

    response = await client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": PLAN_USER_PROMPT.format(
                raw_input=raw_input,
                entities=", ".join(entities) if entities else "无",
                related_text=related_text,
                web_text=web_text,
            )},
        ],
        temperature=settings.temperature,
    )
    return response.choices[0].message.content or ""
