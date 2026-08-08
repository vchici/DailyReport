import json

from openai import AsyncOpenAI

from ..agent.state import Event, EventType
from ..config import Settings

SYSTEM_PROMPT = """你是一个工作事件提取助手。用户会描述当天的工作内容，请提取出关键事件和实体标签。

返回一个 JSON 对象，包含两个字段：
- events: 事件列表，每个事件包含：
  - type: 事件类型，只能是 "meeting"（会议）、"dev"（开发）、"learning"（学习）、"other"（其他）
  - title: 简短标题（不超过15字）
  - detail: 详细描述（不超过50字）
  - priority: 优先级，0=普通, 1=重要
- entities: 从输入中提取的关键实体标签（人名、作品名、项目名、技术名词、工具名等），用于后续检索和关联。每个标签尽量精简（2-6字）

示例输入："上午开了需求评审会，下午修了两个bug，晚上看了Melody Marks的新片"
示例输出：{"events": [{"type": "meeting", "title": "需求评审会", "detail": "参与需求评审会讨论", "priority": 1}, {"type": "dev", "title": "修复2个Bug", "detail": "修复了2个代码Bug", "priority": 0}, {"type": "other", "title": "观看电影", "detail": "观看Melody Marks主演的新片", "priority": 0}], "entities": ["需求评审", "Bug修复", "Melody Marks", "电影"]}

只返回 JSON 对象，不要有其他内容。"""


async def parse_events(
    client: AsyncOpenAI, settings: Settings, raw_text: str
) -> tuple[list[Event], list[str]]:
    """解析用户输入，返回 (事件列表, 实体标签列表)。"""
    response = await client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        temperature=0.3,
    )
    content = response.choices[0].message.content or "{}"
    data = json.loads(content)

    # 兼容旧格式（纯数组）
    if isinstance(data, list):
        events_data = data
        entities = []
    else:
        events_data = data.get("events", [])
        entities = data.get("entities", [])

    events = [
        Event(
            type=EventType(item["type"]),
            title=item["title"],
            detail=item["detail"],
            priority=item.get("priority", 0),
        )
        for item in events_data
    ]
    return events, entities
