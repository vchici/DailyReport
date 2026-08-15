import re

import jieba

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


def tokenize(text: str) -> list[str]:
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
