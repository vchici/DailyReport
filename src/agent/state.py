from dataclasses import dataclass
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
