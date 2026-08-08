from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    MEETING = "meeting"
    DEV = "dev"
    LEARNING = "learning"
    OTHER = "other"


@dataclass
class Event:
    type: EventType
    title: str
    detail: str
    priority: int = 0  # 0=普通, 1=重要


@dataclass
class ReportOutline:
    summary: str
    sections: list[dict] = field(default_factory=list)


@dataclass
class AgentState:
    raw_input: str = ""
    events: list[Event] = field(default_factory=list)
    outline: ReportOutline | None = None
    report: str = ""
    error: str | None = None
