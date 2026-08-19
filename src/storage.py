import json
import os
import sysconfig
from datetime import datetime
from pathlib import Path

from .agent.state import Event
from .config import APP_DIR_NAME
from .tokenizer import tokenize

# 源码运行（本地开发）：项目内 data 目录
_LOCAL_DATA_DIR = Path(__file__).parent.parent / "data"
# pip 安装运行：用户级数据目录（优先 XDG_DATA_HOME，缺省 ~/.local/share）
USER_DATA_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_DIR_NAME

# 按安装方式判断：代码位于 site-packages → pip 安装；否则 → 源码运行
_SITE_PACKAGES = Path(sysconfig.get_paths().get("purelib", ""))
_IS_SOURCE = not Path(__file__).resolve().is_relative_to(_SITE_PACKAGES)

DATA_DIR = _LOCAL_DATA_DIR if _IS_SOURCE else USER_DATA_DIR


def set_data_dir(path: str | None = None) -> Path:
    """按用户配置设置数据目录；未配置/空值回退默认目录。返回最终生效的目录。"""
    global DATA_DIR
    if path and path.strip():
        DATA_DIR = Path(path.strip()).expanduser()
    else:
        DATA_DIR = _LOCAL_DATA_DIR if _IS_SOURCE else USER_DATA_DIR
    return DATA_DIR


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


def load_all_entries() -> list[tuple[str, dict]]:
    """加载所有日期的全部条目（按日期倒序），返回 (日期, 条目) 列表，每条附 _index 字段。"""
    all_entries: list[tuple[str, dict]] = []
    for file_path in sorted(DATA_DIR.glob("*.json"), key=lambda p: p.name, reverse=True):
        if not file_path.stem.startswith("20"):
            continue
        for idx, entry in enumerate(load_entries(file_path.stem)):
            entry["_index"] = idx
            all_entries.append((file_path.stem, entry))
    return all_entries


def save_entries(entries: list[dict], date_str: str | None = None):
    """保存条目到指定日期文件。"""
    file_path = _daily_file(date_str)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def delete_entry(date_str: str, index: int) -> list[dict]:
    """删除指定日期文件中指定索引的条目，返回删除后该日期的剩余条目。"""
    entries = load_entries(date_str)
    if not (0 <= index < len(entries)):
        raise IndexError("条目索引越界")
    entries.pop(index)
    save_entries(entries, date_str)
    return entries


def add_entry(
    raw_input: str,
    events: list[Event],
    entities: list[str] | None = None,
    status: str = "done",
    date_str: str | None = None,
    time_str: str | None = None,
    embedding: list[float] | None = None,
) -> list[dict]:
    """添加一条新记录到指定日期文件，返回该日期全部条目。

    status: "todo"（待办）或 "done"（已完成）
    time_str: 指定时间；缺省时使用当前时间。
    embedding: 实体标签的语义向量（可选），存在 _embedding 字段供向量检索使用。
    """
    entries = load_entries(date_str)
    entry = {
        "time": time_str or datetime.now().strftime("%H:%M"),
        "raw_input": raw_input,
        "status": status,
        "events": [
            {"type": e.type.value, "title": e.title, "detail": e.detail, "priority": e.priority}
            for e in events
        ],
        "entities": entities or [],
        "_tokens": tokenize(raw_input),
    }
    if embedding:
        entry["_embedding"] = embedding
    entries.append(entry)
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
