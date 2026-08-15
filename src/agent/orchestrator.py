from datetime import datetime

from openai import AsyncOpenAI

from ..config import Settings
from ..generation.llm_engine import chat_response, generate_report, generate_suggestion
from ..perception.text_parser import parse_events
from ..retriever import match_done_to_todos, retrieve_related, search_by_text
from ..storage import add_entry, delete_entry, load_all_entries, load_entries, save_entries
from ..web_search import search_web
from .state import Event


class DailyReportAgent:
    """日报 Agent 主控。支持 /plan /done /report /chat 操作，也支持自然语言自动识别。"""

    # 多轮对话保留的消息条数上限（user/assistant 各算一条，即 5 轮）。
    # 仅按"上下文对注意力的影响"权衡：过长历史会稀释模型对当前问题的聚焦。
    MAX_CHAT_HISTORY = 16

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        # 多轮对话历史（user/assistant 交替），仅本次运行内有效
        self.chat_history: list[dict[str, str]] = []

    # ── 自然语言入口 ──

    async def auto_dispatch(self, raw_input: str) -> str:
        """自动识别自然语言输入的意图并分发到对应处理函数。"""
        try:
            intent, events, entities = await parse_events(self.client, self.settings, raw_input)

            if intent == "plan":
                return await self.plan(raw_input, events, entities)
            elif intent == "done":
                return await self.done(raw_input, events, entities)
            elif intent == "chat":
                return await self.chat(raw_input, entities)
            elif intent == "report":
                return await self.generate_daily_report()
            else:
                # 未能识别意图，默认按对话处理
                return await self.chat(raw_input)
        except Exception as e:
            return f"处理失败：{e}"

    # ── 命令处理（接受可选的预解析参数，避免 auto_dispatch 重复调用 LLM）──

    async def plan(self, raw_input: str, events: list[Event] | None = None, entities: list[str] | None = None) -> str:
        """记录待办事项，结合本地历史和联网搜索给出建议方案。"""
        try:
            if events is None or entities is None:
                _, events, entities = await parse_events(self.client, self.settings, raw_input)
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

    async def done(self, raw_input: str, events: list[Event] | None = None, entities: list[str] | None = None) -> str:
        """记录已完成事项，自动匹配当日待办并建立关联。"""
        try:
            if events is None or entities is None:
                _, events, entities = await parse_events(self.client, self.settings, raw_input)
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

    async def edit_entry(self, date_str: str, index: int, raw_input: str) -> str:
        """编辑条目：删除原条目后，按新增逻辑重新添加（保留原日期、时间与状态）。"""
        try:
            entries = load_entries(date_str)
            if not (0 <= index < len(entries)):
                return "索引越界，未找到该条目。"
            status = entries[index].get("status", "done")
            time_str = entries[index].get("time")

            _, events, entities = await parse_events(self.client, self.settings, raw_input)

            delete_entry(date_str, index)
            add_entry(raw_input, events, entities, status=status, date_str=date_str, time_str=time_str)

            self._rebuild_matches(date_str)
            return "✏️ 已更新记录"
        except Exception as e:
            return f"更新失败：{e}"

    def remove_entry(self, date_str: str, index: int) -> str:
        """删除指定条目，并重建当日待办匹配。"""
        try:
            delete_entry(date_str, index)
            self._rebuild_matches(date_str)
            return "🗑️ 已删除记录"
        except Exception as e:
            return f"删除失败：{e}"

    def _rebuild_matches(self, date_str: str) -> None:
        """重建指定日期所有「已完成 → 待办」的匹配关系。"""
        entries = load_entries(date_str)
        todos = [e for e in entries if e.get("status") == "todo"]
        for e in entries:
            if e.get("status") == "done":
                e.pop("matched_todos", None)
                matched = match_done_to_todos(e.get("entities", []), todos)
                if matched:
                    e["matched_todos"] = [t["raw_input"] for t in matched]
        save_entries(entries, date_str)

    async def chat(self, query: str, entities: list[str] | None = None) -> str:
        """自由对话，检索历史 + 联网搜索后回答。"""
        if not query.strip():
            return "请输入你想聊的内容。"

        try:
            if entities is None:
                # 提取实体标签
                _, _, entities = await parse_events(self.client, self.settings, query)

            # 双路检索：实体匹配 + 全文搜索，合并去重
            by_entity = retrieve_related(entities) if entities else []
            by_text = search_by_text(query)
            seen = set()
            related: list[tuple[str, dict]] = []
            for date_str, entry in by_entity + by_text:
                key = (date_str, entry.get("raw_input"))
                if key not in seen:
                    seen.add(key)
                    related.append((date_str, entry))

            # 联网搜索
            search_query = " ".join(entities[:3]) if entities else query[:50]
            web_results = await search_web(search_query, max_results=5)

            response = await chat_response(
                self.client, self.settings, query, related,
                web_results=web_results,
                history=self.chat_history,
            )

            # 追加本轮对话到历史，超出上限则丢弃最旧的
            self.chat_history.append({"role": "user", "content": query})
            self.chat_history.append({"role": "assistant", "content": response})
            if len(self.chat_history) > self.MAX_CHAT_HISTORY:
                self.chat_history = self.chat_history[-self.MAX_CHAT_HISTORY:]

            return response
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

    def list_all_entries(self) -> list[dict]:
        """返回所有日期的全部记录（按日期倒序），供浏览/选择使用。"""
        return load_all_entries()

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
