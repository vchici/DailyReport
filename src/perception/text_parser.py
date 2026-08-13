import json

from openai import AsyncOpenAI

from ..agent.state import Event, EventType
from ..config import Settings

SYSTEM_PROMPT = """你是一个智能助理。分析用户输入，判断意图并提取关键信息。

返回一个 JSON 对象，包含三个字段：
- intent: 用户意图，只能是以下四种之一：
  - "plan": 用户表达了想要/打算/计划做某事（如"想学一下Rust""打算重构代码"）
  - "done": 用户描述已经完成的事（如"今天写完了接口""修了两个bug"）
  - "chat": 用户提问、闲聊或请求建议（如"Rust和Go哪个好""我最近都干了什么"）
  - "report": 用户想要查看日报汇总（如"帮我总结一下""生成日报"）
- events: 事件列表（仅 plan/done 意图时提取，chat/report 时返回空数组），每个事件包含：
  - type: 事件类型，只能是 "meeting"（会议）、"dev"（开发）、"learning"（学习）、"other"（其他）
  - title: 简短标题（不超过15字）
  - detail: 详细描述（不超过50字）
  - priority: 优先级，0=普通, 1=重要
- entities: 从输入中提取的关键实体标签（人名、作品名、项目名、技术名词、工具名等），用于检索和关联。每个标签尽量精简（2-6字）。chat/report 意图也要提取实体会话中涉及的概念。

示例1：
输入："上午开了需求评审会，下午修了两个bug"
输出：{"intent": "done", "events": [{"type": "meeting", "title": "需求评审会", "detail": "参与需求评审会讨论", "priority": 1}, {"type": "dev", "title": "修复2个Bug", "detail": "修复了2个代码Bug", "priority": 0}], "entities": ["需求评审", "Bug修复"]}

示例2：
输入："打算周末学习Rust"
输出：{"intent": "plan", "events": [{"type": "learning", "title": "学习Rust", "detail": "计划周末学习Rust语言", "priority": 0}], "entities": ["Rust", "学习"]}

示例3：
输入："Rust和Go哪个更适合后端开发？"
输出：{"intent": "chat", "events": [], "entities": ["Rust", "Go", "后端开发"]}

只返回 JSON 对象，不要有其他内容。"""


async def parse_events(
    client: AsyncOpenAI, settings: Settings, raw_text: str
) -> tuple[str | None, list[Event], list[str]]:
    """解析用户输入，返回 (intent, 事件列表, 实体标签列表)。

    intent 为 "plan" / "done" / "chat" / "report" 之一。
    """
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
        entities: list[str] = []
        intent: str | None = None
    else:
        events_data = data.get("events", [])
        entities = data.get("entities", [])
        intent = data.get("intent")

    events = [
        Event(
            type=EventType(item["type"]),
            title=item["title"],
            detail=item["detail"],
            priority=item.get("priority", 0),
        )
        for item in events_data
    ]
    return intent, events, entities
