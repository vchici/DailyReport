from datetime import datetime

from openai import AsyncOpenAI

from ..config import Settings
from ..generation.llm_engine import generate_report
from ..generation.renderer import render_report
from ..perception.text_parser import parse_events
from ..storage import add_entry, get_all_events, load_entries
from .planner import plan_report
from .state import AgentState


class DailyReportAgent:
    """日报 Agent 主控。串联 感知→规划→执行→渲染 全流程。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def run(self, raw_input: str) -> str:
        """处理新输入，持久化到当日文件，基于当日全部事件生成日报。"""
        state = AgentState(raw_input=raw_input)

        try:
            # Step 1: 感知 —— 从原始文本提取结构化事件
            state.events = await parse_events(self.client, self.settings, raw_input)

            # Step 2: 持久化 —— 将本次事件存入当日文件
            add_entry(raw_input, state.events)

            # Step 3: 汇总 —— 加载当日全部历史事件
            all_events = get_all_events()

            # Step 4: 规划 —— 根据全部事件生成报告大纲
            state.outline = await plan_report(all_events)

            # Step 5: 执行 —— 基于全部事件调用 LLM 生成日报正文
            state.report = await generate_report(self.client, self.settings, all_events)

            # Step 6: 渲染 —— 套用模板输出最终内容
            return render_report(state.report)

        except Exception as e:
            state.error = str(e)
            raise

    def today_entry_count(self) -> int:
        """获取今日已有记录条数。"""
        return len(load_entries())

    @staticmethod
    def _today_str() -> str:
        """获取今日日期字符串（YYYY-MM-DD）。"""
        return datetime.now().strftime("%Y-%m-%d")
