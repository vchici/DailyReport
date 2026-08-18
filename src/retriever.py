import math
from pathlib import Path
from typing import Optional

from .storage import DATA_DIR, load_entries, save_entries
from .tokenizer import tokenize as _tokenize

# 内存缓存：本次进程生命周期内命中
_cache_mtimes: dict[str, float] = {}
_cache_entries: Optional[list[dict]] = None
_entry_dates: list[str] = []

# 倒排索引：token/entity → 条目下标集合，避免检索时全量扫描
_entity_index: dict[str, set[int]] = {}
_token_index: dict[str, set[int]] = {}

# 实体标签向量：与 _entry_dates 下标一一对应，无向量的条目为 None
_embedding_matrix: list[list[float] | None] = []


async def retrieve_related(
    entities: list[str],
    top_k: int = 5,
    exclude_date: str | None = None,
) -> list[tuple[str, dict]]:
    """按实体标签搜索历史记录，返回 top_k 个 (日期, 条目) 元组。

    entities 来自 LLM 从用户输入中提取的概念词。
    检索时同时用原始标签和分词结果匹配，加权打分；
    若配置了 embedding 且历史条目带向量，则叠加实体向量余弦相似度（混合排序）。
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

    entries = _collect_all_entries()
    query_emb = await _embed_query(entities)
    return _retrieve(entries, query_tokens, top_k, exclude_date, query_emb)


def search_by_text(
    query: str,
    top_k: int = 5,
) -> list[tuple[str, dict]]:
    """全文搜索所有条目的 raw_input 文本，返回 top_k 个 (日期, 条目) 元组。

    query 来自用户原始输入语句，分词后做加权两阶段检索。
    """
    if not query.strip():
        return []

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    entries = _collect_all_entries()
    lex_scores = _score_lexical(query_tokens)
    ranked = sorted(lex_scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(_entry_dates[idx], entries[idx]) for idx, _ in ranked[:top_k]]


def _build_inverted_index(entries: list[dict]) -> None:
    """根据条目列表构建倒排索引（entity 与 token 两套）与实体向量矩阵。"""
    global _entity_index, _token_index, _embedding_matrix

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
    _embedding_matrix = [entry.get("_embedding") for entry in entries]


def _collect_all_entries() -> list[dict]:
    """收集所有日期的全部条目，并同步构建倒排索引。

    用文件 mtime 做内存缓存：同进程内数据未变则直接命中，
    否则重新读取所有日期 JSON（_tokens 已持久化，无需重复分词）。
    """
    global _cache_mtimes, _cache_entries, _entry_dates

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
    entry_dates: list[str] = []
    for file_path_str in sorted(current_mtimes):
        file_path = Path(file_path_str) if file_path_str.startswith("/") else DATA_DIR / file_path_str
        entries = load_entries(file_path.stem)
        needs_save = False
        for entry in entries:
            if "_tokens" not in entry:
                entry["_tokens"] = _tokenize(entry.get("raw_input", ""))
                needs_save = True
            all_entries.append(entry)
            entry_dates.append(file_path.stem)
        if needs_save:
            save_entries(entries, file_path.stem)

    # 更新内存缓存并重建倒排索引
    _cache_mtimes = current_mtimes
    _cache_entries = all_entries
    _entry_dates = entry_dates
    _build_inverted_index(all_entries)

    return all_entries


def _score_lexical(
    query_tokens: set[str],
    exclude_date: str | None = None,
) -> dict[int, int]:
    """两阶段加权打分：概念级（entity）2 倍权重 + 词级（token）1 倍权重。"""
    scores: dict[int, int] = {}
    for qt in query_tokens:
        for idx in _entity_index.get(qt, ()):
            if exclude_date and _entry_dates[idx] == exclude_date:
                continue
            scores[idx] = scores.get(idx, 0) + 2
        for idx in _token_index.get(qt, ()):
            if exclude_date and _entry_dates[idx] == exclude_date:
                continue
            scores[idx] = scores.get(idx, 0) + 1
    return scores


def _cosine(a: list[float], b: list[float]) -> float:
    """两个向量的余弦相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _rank_hybrid(
    lex_scores: dict[int, int],
    query_emb: list[float] | None,
    top_k: int,
    exclude_date: str | None = None,
) -> list[int]:
    """词法分数与实体向量余弦相似度归一化后各占 0.5 加权合并，返回 top_k 个条目下标。

    无向量可用（query_emb 为空或历史条目无向量）时退化为纯词法排序。
    """
    if query_emb is not None and _embedding_matrix:
        candidates = set(lex_scores)
        candidates.update(i for i, v in enumerate(_embedding_matrix) if v is not None)

        max_lex = max(lex_scores.values()) if lex_scores else 0
        combined: dict[int, float] = {}
        for idx in candidates:
            if exclude_date and _entry_dates[idx] == exclude_date:
                continue
            lex_norm = (lex_scores.get(idx, 0) / max_lex) if max_lex else 0.0
            vec = _embedding_matrix[idx]
            cos = _cosine(query_emb, vec) if vec else 0.0
            combined[idx] = 0.5 * lex_norm + 0.5 * cos
        ranked = sorted(combined.items(), key=lambda kv: kv[1], reverse=True)
        return [idx for idx, _ in ranked[:top_k]]

    ranked = sorted(lex_scores.items(), key=lambda kv: kv[1], reverse=True)
    return [idx for idx, _ in ranked[:top_k]]


def _retrieve(
    entries: list[dict],
    query_tokens: set[str],
    top_k: int,
    exclude_date: str | None = None,
    query_emb: list[float] | None = None,
) -> list[tuple[str, dict]]:
    """统一的检索入口：词法加权打分，叠加可选向量相似度后取 top_k。

    通过全局倒排索引定位候选条目，避免全量扫描。
    entries 必须是 _collect_all_entries() 的返回值，
    其下标与倒排索引中的下标一一对应。
    """
    lex_scores = _score_lexical(query_tokens, exclude_date)
    ranked = _rank_hybrid(lex_scores, query_emb, top_k, exclude_date)
    return [(_entry_dates[idx], entries[idx]) for idx in ranked]


async def _embed_query(entities: list[str]) -> list[float] | None:
    """计算查询实体标签的向量；未配置或调用失败时返回 None（降级为纯词法）。"""
    if not entities:
        return None
    try:
        from .config import Settings
        from .embedding import embed_entities

        return await embed_entities(Settings(), entities)
    except Exception:
        return None


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
