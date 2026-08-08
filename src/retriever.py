from datetime import datetime
from pathlib import Path

from .storage import DATA_DIR, load_entries


def retrieve_related(
    entities: list[str],
    top_k: int = 5,
    today: str | None = None,
) -> list[dict]:
    """搜索所有历史记录中与给定实体标签相关的条目。

    遍历 data/ 下所有 JSON 文件，按 entities 交集数量排序，
    返回 top_k 条最相关的历史记录。
    """
    if not entities:
        return []

    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    query_set = set(e.lower().strip() for e in entities if e.strip())
    if not query_set:
        return []

    # 收集所有历史条目，过滤空实体的条目
    all_entries: list[dict] = []
    for file_path in sorted(DATA_DIR.glob("*.json")):
        if not file_path.stem.startswith("20"):  # 跳过非日期文件
            continue
        entries = load_entries(file_path.stem)
        for entry in entries:
            entry.setdefault("date", file_path.stem)
            all_entries.append(entry)

    # 计算交集得分，排序（排除今日条目）
    scored: list[tuple[int, dict]] = []
    for entry in all_entries:
        if entry.get("date") == today:
            continue
        entry_entities = set(e.lower().strip() for e in entry.get("entities", []))
        if not entry_entities:
            continue
        overlap = len(query_set & entry_entities)
        if overlap > 0:
            scored.append((overlap, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]
