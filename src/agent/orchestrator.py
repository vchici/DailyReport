from datetime import datetime

from openai import AsyncOpenAI

from ..config import Settings
from ..generation.llm_engine import chat_response, generate_report, generate_suggestion
from ..perception.text_parser import parse_events
from ..retriever import match_done_to_todos, retrieve_related, search_by_text
from ..storage import add_entry, load_entries, save_entries
from ..web_search import search_web


class DailyReportAgent:
    """日报 Agent 主控。支持 /plan /done /report /chat 操作。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def plan(self, raw_input: str) -> str:
        """记录待办事项，结合本地历史和联网搜索给出建议方案。"""
        try:
            events, entities = await parse_events(self.client, self.settings, raw_input)
            add_entry(raw_input, events, entities, status="todo")

            related = retrieve_related(entities)
            query = " ".join(entities[:3]) if entities else raw_input[:50]
            web_results = await search_web(query, max_results=5)

            suggestion = await generate_suggestion(
                self.client, self.settings, raw_input, entities, related,
                web_results=web_results,
            )
            return f"📋 已记录待办\n\n{suggestion}"
        except Exception as e:
            return f"记录失败：{e}"

    async def done(self, raw_input: str) -> str:
        """记录已完成事项，自动匹配当日待办并建立关联。"""
        try:
            events, entities = await parse_events(self.client, self.settings, raw_input)
            entries = add_entry(raw_input, events, entities, status="done")

            # 匹配当日待办：用 done 的实体标签对比 todo 条目
            todos = [e for e in entries if e.get("status") == "todo"]
            matched = match_done_to_todos(entities, todos)

            if matched:
                # 将匹配关系写入 done 条目
                entries[-1]["matched_todos"] = [t["raw_input"] for t in matched]
                save_entries(entries)

            done_count = sum(1 for e in entries if e.get("status") == "done")
            msg = f"✅ 已记录完成（今日共 {done_count} 项）"
            if matched:
                names = "、".join(t["raw_input"][:30] for t in matched)
                msg += f"\n🔗 匹配待办：{names}"
            return msg
        except Exception as e:
            return f"记录失败：{e}"

    async def chat(self, query: str) -> str:
        """自由对话，检索历史 + 联网搜索后回答。"""
        if not query.strip():
            return "请输入你想聊的内容。"

        try:
            # 提取实体标签
            _, entities = await parse_events(self.client, self.settings, query)

            # 双路检索：实体匹配 + 全文搜索，合并去重
            by_entity = retrieve_related(entities) if entities else []
            by_text = search_by_text(query)
            seen = set()
            related: list[dict] = []
            for entry in by_entity + by_text:
                key = (entry.get("date"), entry.get("raw_input"))
                if key not in seen:
                    seen.add(key)
                    related.append(entry)

            # 联网搜索
            search_query = " ".join(entities[:3]) if entities else query[:50]
            web_results = await search_web(search_query, max_results=5)

            return await chat_response(
                self.client, self.settings, query, related,
                web_results=web_results,
            )
        except Exception as e:
            return f"对话出错：{e}"

    async def generate_daily_report(self) -> str:
        """生成当日完整日报（合并待办和已完成，含历史关联发现）。"""
        entries = load_entries()
        if not entries:
            return "今日暂无记录。"

        all_entities: list[str] = []
        for entry in entries:
            all_entities.extend(entry.get("entities", []))

        related = retrieve_related(all_entities, exclude_date=self._today_str()) if all_entities else []

        try:
            report = await generate_report(
                self.client, self.settings, entries,
                related_entries=related,
            )
            return report
        except Exception as e:
            return f"日报生成失败：{e}"

    def today_entry_count(self) -> int:
        return len(load_entries())

    def today_summary(self) -> str:
        entries = load_entries()
        todo_count = sum(1 for e in entries if e.get("status") == "todo")
        done_count = sum(1 for e in entries if e.get("status") == "done")
        parts = []
        if done_count:
            parts.append(f"已完成 {done_count} 项")
        if todo_count:
            parts.append(f"待办 {todo_count} 项")
        return "，".join(parts) if parts else "暂无记录"

    @staticmethod
    def _today_str() -> str:
        return datetime.now().strftime("%Y-%m-%d")
