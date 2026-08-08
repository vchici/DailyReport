import json

from openai import AsyncOpenAI

from ..agent.state import Event, EventType
from ..config import Settings

SYSTEM_PROMPT = """你是一个工作事件提取助手。用户会描述一天的工作内容，请提取出关键事件。

返回 JSON 格式的事件列表，每个事件包含：
- type: 事件类型，只能是 "meeting"（会议）、"dev"（开发）、"learning"（学习）、"other"（其他）
- title: 简短标题（不超过15字）
- detail: 详细描述（不超过50字）
- priority: 优先级，0=普通, 1=重要

示例输入："上午开了需求评审会，下午修了两个bug"
示例输出：[{"type": "meeting", "title": "需求评审会", "detail": "参与需求评审会讨论", "priority": 1}, {"type": "dev", "title": "修复2个Bug", "detail": "修复了2个代码Bug", "priority": 0}]

只返回 JSON 数组，不要有其他内容。"""


async def parse_events(
    client: AsyncOpenAI, settings: Settings, raw_text: str
) -> list[Event]:
    response = await client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        temperature=0.3,
    )
    content = response.choices[0].message.content or "[]"
    data = json.loads(content)
    return [
        Event(
            type=EventType(item["type"]),
            title=item["title"],
            detail=item["detail"],
            priority=item.get("priority", 0),
        )
        for item in data
    ]
