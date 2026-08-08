import asyncio
import sys

# 添加第三方包路径（sandbox 环境兼容）
sys.path.insert(0, r"d:\Projects\KnowledgeBase\.packages")

from src.config import Settings
from src.agent.orchestrator import DailyReportAgent


async def main():
    settings = Settings()
    agent = DailyReportAgent(settings)

    print("=" * 50)
    print("  日报 Agent — 输入你今天的工作内容")
    print("=" * 50)
    print()

    print("请输入今日工作内容（每行一条，输入空行结束）：")
    lines = []
    while True:
        line = input()
        if line.strip() == "":
            break
        lines.append(line)
    raw_input = "\n".join(lines)

    if not raw_input.strip():
        print("输入为空，退出。")
        return

    print("\n⏳ 正在生成日报...\n")

    try:
        report = await agent.run(raw_input)
        print("=" * 50)
        print(report)
        print("=" * 50)
    except Exception as e:
        print(f"生成失败：{e}")


if __name__ == "__main__":
    asyncio.run(main())
