import asyncio
from concurrent.futures import ThreadPoolExecutor

from ddgs import DDGS


def _search_sync(query: str, max_results: int = 5) -> list[dict]:
    """同步搜索（在独立线程中运行），使用上下文管理器自动释放资源。"""
    results: list[dict] = []
    with DDGS() as ddgs:
        try:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        except Exception:
            pass
    return results


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """异步联网搜索，返回 [{title, url, snippet}, ...]。"""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, _search_sync, query, max_results)
