import math

from openai import AsyncOpenAI

from .config import Settings


def _normalize(vec: list[float]) -> list[float]:
    """L2 归一化，使向量长度恒为 1（余弦相似度等价于点积）。"""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


async def embed_texts(settings: Settings, texts: list[str]) -> list[list[float]]:
    """批量计算文本向量（硅基流动 OpenAI 兼容接口）。

    返回与 texts 一一对应的向量列表；未配置 Key、参数为空或调用失败时返回空列表。
    调用方应把空结果视为"语义检索不可用"，优雅降级为纯词法检索。
    """
    if not settings.siliconflow_api_key or not texts:
        return []
    try:
        client = AsyncOpenAI(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
        )
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [d.embedding for d in resp.data]
    except Exception:
        return []


async def embed_entities(settings: Settings, entities: list[str]) -> list[float] | None:
    """把一组实体标签表示为一个向量：每个实体独立 embed，L2 归一化后逐分量平均再归一化。

    业界常用的 mean pooling 方案，避免把多个概念拼成一句话导致语义互相稀释。
    未配置 Key、失败或结果异常时返回 None，调用方应优雅降级为纯词法检索。
    """
    if not settings.siliconflow_api_key or not entities:
        return None
    vecs = await embed_texts(settings, entities)  # 批量一次调用
    if len(vecs) != len(entities) or not vecs:
        return None
    dim = len(vecs[0])
    if any(len(v) != dim for v in vecs):
        return None
    pooled = [0.0] * dim
    for vec in vecs:
        for i, x in enumerate(_normalize(vec)):
            pooled[i] += x
    pooled = [x / len(vecs) for x in pooled]
    return _normalize(pooled)
