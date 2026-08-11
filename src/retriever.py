import re

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


def _tokenize(text: str) -> list[str]:
    """用 jieba 分词，去停用词和单字、标点，返回归一化词列表。"""
    # 先对纯英文/数字片段做保护（保留大小写原始值给 lower 统一处理），
    # jieba 对中英混排直接 cut 即可
    words: list[str] = []
    for w in jieba.cut(text):
        w = w.strip().lower()
        if not w:
            continue
        # 过滤纯标点/空白、单字符（英文单字母）、停用词
        if len(w) < 2:
            continue
        if re.fullmatch(r"[\W_]+", w):
            continue
        if w in _STOP_WORDS:
            continue
        words.append(w)
    # 去重保留顺序无关紧要，但保留重复词不影响 set 交集
    return words


def retrieve_related(
    entities: list[str],
    top_k: int = 5,
    exclude_date: str | None = None,
) -> list[dict]:
    """按实体标签搜索历史记录，返回 top_k 最相关条目。"""
    if not entities:
        return []

    query_set = set(e.lower().strip() for e in entities if e.strip())
    if not query_set:
        return []

    all_entries = _collect_all_entries()
    return _score_and_rank(all_entries, query_set, top_k, exclude_date=exclude_date)


def search_by_text(
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """全文搜索所有条目的 raw_input 文本，不依赖实体标签。

    使用 jieba 分词，同时对 query 和每条记录的 raw_input 做分词，
    以词集交集大小作为相关性得分，天然支持中英混排场景。
    """
    if not query.strip():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    query_set = set(query_tokens)
    all_entries = _collect_all_entries()

    scored: list[tuple[int, dict]] = []
    for entry in all_entries:
        raw_tokens = entry.get("_tokens", [])
        if not raw_tokens:
            continue
        score = len(query_set & set(raw_tokens))
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]


def _collect_all_entries() -> list[dict]:
    """收集所有日期的全部条目，按需分词并持久化缓存到 JSON 文件。

    已有 _tokens 的条目直接复用；新增/未分词的条目在分词后
    写回对应日期文件，后续加载不再重复分词。
    """
    all_entries: list[dict] = []
    for file_path in sorted(DATA_DIR.glob("*.json")):
        if not file_path.stem.startswith("20"):
            continue
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
    return all_entries


def _score_and_rank(
    entries: list[dict],
    query_set: set[str],
    top_k: int,
    exclude_date: str | None = None,
) -> list[dict]:
    """按实体交集得分排序。"""
    scored: list[tuple[int, dict]] = []
    for entry in entries:
        if exclude_date and entry.get("date") == exclude_date:
            continue
        entry_entities = set(e.lower().strip() for e in entry.get("entities", []))
        if not entry_entities:
            continue
        overlap = len(query_set & entry_entities)
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]
