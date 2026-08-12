import json
import re
from pathlib import Path
from typing import Optional

import jieba

from .storage import DATA_DIR, load_entries, save_entries

# 中文常见停用词 + 英文单字母，分词后过滤
_STOP_WORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "什么", "怎么", "如何", "为什么", "可以", "这个", "那个", "所以",
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "and", "or", "but", "not", "no", "if", "so", "as", "it",
    "this", "that", "these", "those", "i", "we", "you", "he", "she",
}

# 内存缓存：本次进程生命周期内命中
_cache_mtimes: dict[str, float] = {}
_cache_entries: Optional[list[dict]] = None

# 磁盘持久化缓存：跨进程/重启后命中
_INDEX_CACHE_PATH = DATA_DIR / "_index_cache.json"


def _tokenize(text: str) -> list[str]:
    """用 jieba 分词，去停用词和单字、标点，返回归一化词列表。"""
    words: list[str] = []
    for w in jieba.cut(text):
        w = w.strip().lower()
        if not w:
            continue
        if len(w) < 2:
            continue
        if re.fullmatch(r"[\W_]+", w):
            continue
        if w in _STOP_WORDS:
            continue
        words.append(w)
    return words


def retrieve_related(
    entities: list[str],
    top_k: int = 5,
    exclude_date: str | None = None,
) -> list[dict]:
    """按实体标签搜索历史记录，返回 top_k 最相关条目。

    entities 来自 LLM 从用户输入中提取的概念词。
    检索时同时用原始标签和分词结果匹配，加权打分。
    """
    if not entities:
        return []

    # 同时保留原始标签（精确概念匹配）和分词结果（宽泛词级匹配）
    query_tokens: set[str] = set()
    for e in entities:
        e_lower = e.lower().strip()
        if not e_lower:
            continue
        query_tokens.add(e_lower)
        query_tokens.update(_tokenize(e_lower))

    if not query_tokens:
        return []

    return _retrieve(_collect_all_entries(), query_tokens, top_k, exclude_date)


def search_by_text(
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """全文搜索所有条目的 raw_input 文本。

    query 来自用户原始输入语句，分词后做加权两阶段检索。
    """
    if not query.strip():
        return []

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    return _retrieve(_collect_all_entries(), query_tokens, top_k)


def _collect_all_entries() -> list[dict]:
    """收集所有日期的全部条目，两层缓存：内存 + 磁盘。

    1. 内存缓存命中 → 直接返回（同进程内最快）
    2. 磁盘缓存命中 → 加载 _index_cache.json（跨重启）
    3. 缓存失效 → 全量重建，并同时写回磁盘缓存
    """
    global _cache_mtimes, _cache_entries

    # ── 先收集当前所有 JSON 文件的 mtime ──
    current_mtimes: dict[str, float] = {}
    for file_path in sorted(DATA_DIR.glob("*.json")):
        if not file_path.stem.startswith("20"):
            continue
        current_mtimes[str(file_path)] = file_path.stat().st_mtime

    # ── 第一层：内存缓存（同进程内的瞬时命中）──
    if _cache_entries is not None and current_mtimes == _cache_mtimes:
        return _cache_entries

    # ── 第二层：磁盘持久化缓存（跨重启命中）──
    if _INDEX_CACHE_PATH.exists():
        try:
            with open(_INDEX_CACHE_PATH, "r", encoding="utf-8") as f:
                disk = json.load(f)
            if disk.get("mtimes") == current_mtimes:
                _cache_mtimes = current_mtimes
                _cache_entries = disk["entries"]
                return _cache_entries
        except (json.JSONDecodeError, KeyError):
            pass  # 缓存文件损坏，降级重建

    # ── 缓存未命中，全量重建 ──
    all_entries: list[dict] = []
    for file_path_str in sorted(current_mtimes):
        file_path = Path(file_path_str) if file_path_str.startswith("/") else DATA_DIR / file_path_str
        entries = load_entries(file_path.stem)
        needs_save = False
        for entry in entries:
            entry.setdefault("date", file_path.stem)
            if "_tokens" not in entry:
                entry["_tokens"] = _tokenize(entry.get("raw_input", ""))
                needs_save = True
            all_entries.append(entry)
        if needs_save:
            save_entries(entries, file_path.stem)

    # 写回两层缓存
    _cache_mtimes = current_mtimes
    _cache_entries = all_entries
    with open(_INDEX_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"mtimes": current_mtimes, "entries": all_entries}, f, ensure_ascii=False)

    return all_entries


def _retrieve(
    entries: list[dict],
    query_tokens: set[str],
    top_k: int,
    exclude_date: str | None = None,
) -> list[dict]:
    """统一的加权两阶段检索。

    第一阶段 query_tokens × entities —— 概念级匹配，2倍权重
    第二阶段 query_tokens × _tokens —— 词级匹配，1倍权重
    加权总分排序后返回 top_k。
    """
    scored: list[tuple[int, dict]] = []
    for entry in entries:
        if exclude_date and entry.get("date") == exclude_date:
            continue
        # 第一阶段：与条目的 entity 标签做交集
        entry_entities = set(e.lower().strip() for e in entry.get("entities", []))
        entity_hits = len(query_tokens & entry_entities)
        # 第二阶段：与条目的 _tokens 做交集
        token_hits = len(query_tokens & set(entry.get("_tokens", [])))

        score = entity_hits * 2 + token_hits
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]


def match_done_to_todos(
    done_entities: list[str],
    todos: list[dict],
    threshold: int = 1,
) -> list[dict]:
    """用实体标签匹配已完成事项到当日待办，返回命中的待办列表。

    复用与检索相同的加权两阶段算法：
    - 第一阶段：done_entities × todo.entities（精确概念匹配，2倍权重）
    - 第二阶段：分词结果匹配（宽泛词级匹配，1倍权重）
    - 加权总分 >= threshold 即视为匹配
    """
    if not done_entities or not todos:
        return []

    # 构建查询 token 集合（和 retrieve_related 一致）
    query_tokens: set[str] = set()
    for e in done_entities:
        e_lower = e.lower().strip()
        if not e_lower:
            continue
        query_tokens.add(e_lower)
        query_tokens.update(_tokenize(e_lower))

    if not query_tokens:
        return []

    # 对每个待办条目打分
    scored: list[tuple[int, dict]] = []
    for todo in todos:
        todo_entities = set(e.lower().strip() for e in todo.get("entities", []))
        entity_hits = len(query_tokens & todo_entities)

        # 对待办做即时分词（待办数据量小，无需全局缓存）
        if "_tokens" not in todo:
            todo["_tokens"] = _tokenize(todo.get("raw_input", ""))
        token_hits = len(query_tokens & set(todo.get("_tokens", [])))

        score = entity_hits * 2 + token_hits
        if score >= threshold:
            scored.append((score, todo))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [todo for _, todo in scored]
