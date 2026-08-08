import asyncio
import sys

# 添加第三方包路径（sandbox 环境兼容）
sys.path.insert(0, r"d:\Projects\KnowledgeBase\.packages")

from src.config import Settings
from src.agent.orchestrator import DailyReportAgent


HELP_TEXT = """命令说明：
  /plan <内容>   记录待办事项，Agent 会基于历史给出建议
  /done <内容>   记录已完成事项
  /report        生成本日完整日报
  /status        查看今日概况
  /help          显示此帮助
  /exit          退出"""


async def main():
    settings = Settings()
    agent = DailyReportAgent(settings)

    print("=" * 50)
    print("  日报 Agent")
    print("  /plan 待办  |  /done 完成  |  /report 日报")
    print("  输入 /help 查看帮助")
    print("=" * 50)
    print()

    while True:
        try:
            cmd_line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not cmd_line:
            continue

        # 解析命令
        if cmd_line.startswith("/plan "):
            content = cmd_line[6:].strip()
            if not content:
                print("请输入计划内容，如：/plan 今天要在朴朴下单xxx菜，...\n")
                continue
            print("\n⏳ 正在分析...\n")
            result = await agent.plan(content)
            print(result)

            # 询问是否保存建议
            try:
                save = input("\n是否保存建议到本地？(y/n，直接回车默认 y): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                save = "n"
            if save in ("", "y", "yes"):
                from src.storage import append_plan_suggestion
                path = append_plan_suggestion(f"## 计划\n\n{result}", agent._today_str())
                print(f"✓ 已保存到 {path}")
            print()

        elif cmd_line.startswith("/done "):
            content = cmd_line[6:].strip()
            if not content:
                print("请输入完成内容，如：/done 看了xx电影，感觉...\n")
                continue
            print("\n⏳ 正在记录...\n")
            result = await agent.done(content)
            print(result)
            print()

        elif cmd_line == "/report":
            summary = agent.today_summary()
            print(f"\n⏳ 正在生成日报（{summary}）...\n")
            report = await agent.generate_daily_report()
            print("=" * 50)
            print(report)
            print("=" * 50)

            # 询问是否保存
            try:
                save = input("\n是否保存到本地？(y/n，直接回车默认 y): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                save = "n"
            if save in ("", "y", "yes"):
                from src.storage import save_daily_report
                path = save_daily_report(report, agent._today_str())
                print(f"✓ 已保存到 {path}")
            print()

        elif cmd_line == "/status":
            summary = agent.today_summary()
            print(f"\n今日概况：{summary}\n")
            entries = agent.today_entry_count()
            if entries > 0:
                print(f"共 {entries} 条记录，存储于 data/{agent._today_str()}.json\n")

        elif cmd_line == "/help":
            print(f"\n{HELP_TEXT}\n")

        elif cmd_line == "/exit":
            print("再见！")
            break

        else:
            print(f"未知命令：{cmd_line}")
            print(f"可用命令：/plan /done /report /status /help /exit\n")


if __name__ == "__main__":
    asyncio.run(main())
