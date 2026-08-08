from openai import AsyncOpenAI

from ..config import Settings
from ..generation.llm_engine import generate_report
from ..generation.renderer import render_report
from ..perception.text_parser import parse_events
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
        state = AgentState(raw_input=raw_input)

        try:
            # Step 1: 感知 —— 从原始文本提取结构化事件
            state.events = await parse_events(self.client, self.settings, raw_input)

            # Step 2: 规划 —— 根据事件生成报告大纲
            state.outline = await plan_report(state.events)

            # Step 3: 执行 —— 调用 LLM 生成日报正文
            state.report = await generate_report(self.client, self.settings, state.events)

            # Step 4: 渲染 —— 套用模板输出最终内容
            return render_report(state.report)

        except Exception as e:
            state.error = str(e)
            raise
