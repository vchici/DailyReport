import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor

from ddgs import DDGS


def _search_sync(query: str, max_results: int = 5) -> list[dict]:
    """同步搜索（在独立线程中运行）。"""
    results: list[dict] = []
    ddgs = DDGS()
    try:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
    except Exception:
        pass
    finally:
        # 显式关闭内部 HTTP session，释放连接池
        for attr in ("session", "_session", "client", "_client", "http_client"):
            obj = getattr(ddgs, attr, None)
            if obj is not None and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception:
                    pass
    return results


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """异步联网搜索，返回 [{title, url, snippet}, ...]。"""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = await loop.run_in_executor(pool, _search_sync, query, max_results)
    # 线程池关闭后强制 GC，清理子线程中残留的 socket 连接
    gc.collect()
    return result
