from datetime import datetime

from openai import AsyncOpenAI

from ..config import Settings
from ..generation.llm_engine import generate_report, generate_suggestion
from ..generation.renderer import render_report
from ..perception.text_parser import parse_events
from ..retriever import retrieve_related
from ..storage import add_entry, get_today_entries, load_entries


class DailyReportAgent:
    """日报 Agent 主控。支持 /plan /done /report 三种操作。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def plan(self, raw_input: str) -> str:
        """记录待办事项，基于历史关联给出建议方案。"""
        try:
            # 解析事件和实体
            events, entities = await parse_events(self.client, self.settings, raw_input)

            # 持久化为待办
            add_entry(raw_input, events, entities, status="todo")

            # 检索历史关联
            related = retrieve_related(entities)

            # 生成建议
            suggestion = await generate_suggestion(
                self.client, self.settings, raw_input, entities, related,
            )
            return f"📋 已记录待办\n\n{suggestion}"
        except Exception as e:
            return f"记录失败：{e}"

    async def done(self, raw_input: str) -> str:
        """记录已完成事项。"""
        try:
            events, entities = await parse_events(self.client, self.settings, raw_input)

            add_entry(raw_input, events, entities, status="done")

            # 统计今日完成数
            entries = get_today_entries()
            done_count = sum(1 for e in entries if e.get("status") == "done")
            return f"✅ 已记录完成（今日共 {done_count} 项）"
        except Exception as e:
            return f"记录失败：{e}"

    async def generate_daily_report(self) -> str:
        """生成当日完整日报（合并待办和已完成，含历史关联发现）。"""
        entries = get_today_entries()
        if not entries:
            return "今日暂无记录。"

        # 汇总已完成事项的实体用于检索
        all_entities: list[str] = []
        for entry in entries:
            if entry.get("status") == "done":
                all_entities.extend(entry.get("entities", []))

        related = retrieve_related(all_entities) if all_entities else []

        try:
            report = await generate_report(
                self.client, self.settings, entries,
                related_entries=related,
            )
            return render_report(report)
        except Exception as e:
            return f"日报生成失败：{e}"

    def today_entry_count(self) -> int:
        """获取今日已有记录条数。"""
        return len(load_entries())

    def today_summary(self) -> str:
        """获取今日概况（待办/完成数量）。"""
        entries = get_today_entries()
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
        """获取今日日期字符串（YYYY-MM-DD）。"""
        return datetime.now().strftime("%Y-%m-%d")
