import json
from datetime import datetime
from pathlib import Path

from .agent.state import Event

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


def add_entry(
    raw_input: str,
    events: list[Event],
    entities: list[str] | None = None,
    status: str = "done",
    date_str: str | None = None,
) -> list[dict]:
    """添加一条新记录到当日文件，返回当日全部条目。

    status: "todo"（待办）或 "done"（已完成）
    """
    entries = load_entries(date_str)
    entries.append({
        "time": datetime.now().strftime("%H:%M"),
        "raw_input": raw_input,
        "status": status,
        "events": [
            {"type": e.type.value, "title": e.title, "detail": e.detail, "priority": e.priority}
            for e in events
        ],
        "entities": entities or [],
    })
    save_entries(entries, date_str)
    return entries


def save_daily_report(content: str, date_str: str | None = None) -> Path:
    """将日报保存为 Markdown 文件，返回保存路径。"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    reports_dir = DATA_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    file_path = reports_dir / f"{date_str}.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


def append_plan_suggestion(content: str, date_str: str | None = None) -> Path:
    """将 /plan 的建议追加保存到当日计划文件（Markdown）。"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    plans_dir = DATA_DIR / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    file_path = plans_dir / f"{date_str}.md"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(content)
        f.write("\n\n---\n\n")
    return file_path
