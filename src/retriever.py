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
