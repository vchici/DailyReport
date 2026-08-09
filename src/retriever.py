from datetime import datetime
from pathlib import Path

from .storage import DATA_DIR, load_entries


def retrieve_related(
    entities: list[str],
    top_k: int = 5,
    today: str | None = None,
) -> list[dict]:
    """按实体标签搜索历史记录，返回 top_k 最相关条目。"""
    if not entities:
        return []

    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    query_set = set(e.lower().strip() for e in entities if e.strip())
    if not query_set:
        return []

    all_entries = _collect_all_entries()
    return _score_and_rank(all_entries, query_set, top_k)


def search_by_text(
    query: str,
    top_k: int = 5,
    today: str | None = None,
) -> list[dict]:
    """全文搜索所有条目的 raw_input 文本，不依赖实体标签。"""
    if not query.strip():
        return []

    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    query_lower = query.lower()
    # 拆成关键词，过滤太短的
    keywords = [w for w in query_lower.split() if len(w) >= 2]

    all_entries = _collect_all_entries()

    # 按关键词命中数评分
    scored: list[tuple[int, dict]] = []
    for entry in all_entries:
        raw = entry.get("raw_input", "").lower()
        score = sum(1 for kw in keywords if kw in raw)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]


def _collect_all_entries() -> list[dict]:
    """收集所有日期的全部条目。"""
    all_entries: list[dict] = []
    for file_path in sorted(DATA_DIR.glob("*.json")):
        if not file_path.stem.startswith("20"):
            continue
        entries = load_entries(file_path.stem)
        for entry in entries:
            entry.setdefault("date", file_path.stem)
            all_entries.append(entry)
    return all_entries


def _score_and_rank(
    entries: list[dict], query_set: set[str], top_k: int,
) -> list[dict]:
    """按实体交集得分排序。"""
    scored: list[tuple[int, dict]] = []
    for entry in entries:
        entry_entities = set(e.lower().strip() for e in entry.get("entities", []))
        if not entry_entities:
            continue
        overlap = len(query_set & entry_entities)
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]
