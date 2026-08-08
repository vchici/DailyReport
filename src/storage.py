import json
from datetime import datetime
from pathlib import Path

from .agent.state import Event, EventType

DATA_DIR = Path(__file__).parent.parent / "data"


def _daily_file(date_str: str | None = None) -> Path:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return DATA_DIR / f"{date_str}.json"


def load_entries(date_str: str | None = None) -> list[dict]:
    """加载指定日期的所有条目。"""
    file_path = _daily_file(date_str)
    if not file_path.exists():
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_entries(entries: list[dict], date_str: str | None = None):
    """保存条目到指定日期文件。"""
    file_path = _daily_file(date_str)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def add_entry(raw_input: str, events: list[Event], entities: list[str] | None = None, date_str: str | None = None) -> list[dict]:
    """添加一条新记录到当日文件，返回当日全部条目。"""
    entries = load_entries(date_str)
    entries.append({
        "time": datetime.now().strftime("%H:%M"),
        "raw_input": raw_input,
        "events": [
            {"type": e.type.value, "title": e.title, "detail": e.detail, "priority": e.priority}
            for e in events
        ],
        "entities": entities or [],
    })
    save_entries(entries, date_str)
    return entries


def get_all_events(date_str: str | None = None) -> list[Event]:
    """获取指定日期的全部事件（跨所有条目合并）。"""
    entries = load_entries(date_str)
    all_events: list[Event] = []
    for entry in entries:
        for e in entry.get("events", []):
            all_events.append(Event(
                type=EventType(e["type"]),
                title=e["title"],
                detail=e["detail"],
                priority=e.get("priority", 0),
            ))
    return all_events
