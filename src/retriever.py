import re
from pathlib import Path
from typing import Optional

import jieba

from .storage import DATA_DIR, load_entries, save_entries

# 关闭 jieba 的词典加载日志（Building prefix dict 那几行噪音）
jieba.setLogLevel(20)

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

# 倒排索引：token/entity → 条目下标集合，避免检索时全量扫描
_entity_index: dict[str, set[int]] = {}
_token_index: dict[str, set[int]] = {}


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


def _build_inverted_index(entries: list[dict]) -> None:
    """根据条目列表构建倒排索引（entity 与 token 两套）。"""
    global _entity_index, _token_index

    entity_index: dict[str, set[int]] = {}
    token_index: dict[str, set[int]] = {}
    for idx, entry in enumerate(entries):
        for e in entry.get("entities", []):
            e_lower = e.lower().strip()
            if e_lower:
                entity_index.setdefault(e_lower, set()).add(idx)
        for t in entry.get("_tokens", []):
            token_index.setdefault(t, set()).add(idx)
    _entity_index = entity_index
    _token_index = token_index


def _collect_all_entries() -> list[dict]:
    """收集所有日期的全部条目，并同步构建倒排索引。

    用文件 mtime 做内存缓存：同进程内数据未变则直接命中，
    否则重新读取所有日期 JSON（_tokens 已持久化，无需重复分词）。
    """
    global _cache_mtimes, _cache_entries

    # ── 先收集当前所有 JSON 文件的 mtime ──
    current_mtimes: dict[str, float] = {}
    for file_path in sorted(DATA_DIR.glob("*.json")):
        if not file_path.stem.startswith("20"):
            continue
        current_mtimes[str(file_path)] = file_path.stat().st_mtime

    # ── 内存缓存命中：同进程内数据未变，直接返回 ──
    if _cache_entries is not None and current_mtimes == _cache_mtimes:
        return _cache_entries

    # ── 缓存失效，重新读取所有日期文件 ──
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

    # 更新内存缓存并重建倒排索引
    _cache_mtimes = current_mtimes
    _cache_entries = all_entries
    _build_inverted_index(all_entries)

    return all_entries


def _retrieve(
    entries: list[dict],
    query_tokens: set[str],
    top_k: int,
    exclude_date: str | None = None,
) -> list[dict]:
    """统一的加权两阶段检索（倒排索引加速）。

    第一阶段 query_tokens × entities —— 概念级匹配，2倍权重
    第二阶段 query_tokens × _tokens —— 词级匹配，1倍权重
    加权总分排序后返回 top_k。

    通过全局倒排索引定位候选条目，避免全量扫描。
    entries 必须是 _collect_all_entries() 的返回值，
    其下标与倒排索引中的下标一一对应。
    """
    scores: dict[int, int] = {}
    for qt in query_tokens:
        for idx in _entity_index.get(qt, ()):
            if exclude_date and entries[idx].get("date") == exclude_date:
                continue
            scores[idx] = scores.get(idx, 0) + 2
        for idx in _token_index.get(qt, ()):
            if exclude_date and entries[idx].get("date") == exclude_date:
                continue
            scores[idx] = scores.get(idx, 0) + 1

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [entries[idx] for idx, _ in ranked[:top_k]]


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
