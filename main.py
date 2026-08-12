import asyncio

from src.config import Settings
from src.agent.orchestrator import DailyReportAgent


HELP_TEXT = """命令说明：
  /plan          记录待办事项（多行输入，以单独的 . 结束）
  /done          记录已完成事项（多行输入，以单独的 . 结束）
  /chat <内容>   自由对话，Agent 会检索历史记录和联网信息回答
  /report        生成本日完整日报
  /status        查看今日概况
  /help          显示此帮助
  /exit          退出"""


def read_multiline(first_line: str = "") -> str:
    """读取多行输入，以单独的 . 行结束。"""
    lines: list[str] = []
    if first_line:
        lines.append(first_line)
    while True:
        try:
            line = input("  ")
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == ".":
            break
        lines.append(line)
    return "\n".join(lines)


async def main():
    settings = Settings()
    agent = DailyReportAgent(settings)

    print("=" * 50)
    print("  日报 Agent")
    print("  /plan 待办  |  /done 完成  |  /chat 对话  |  /report 日报")
    print("  多行输入以单独 . 结束  |  /help 查看帮助")
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
        if cmd_line.startswith("/plan"):
            content = read_multiline(cmd_line.removeprefix("/plan").strip())
            if not content:
                print("内容为空，跳过。\n")
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

        elif cmd_line.startswith("/done"):
            content = read_multiline(cmd_line.removeprefix("/done").strip())
            if not content:
                print("内容为空，跳过。\n")
                continue
            print("\n⏳ 正在记录...\n")
            result = await agent.done(content)
            print(result)
            print()

        elif cmd_line.startswith("/chat"):
            content = cmd_line.removeprefix("/chat").strip()
            if not content:
                print("请输入你想聊的内容，如：/chat 我最近看过哪些影视作品？\n")
                continue
            print(f"\n⏳ 正在思考...\n")
            result = await agent.chat(content)
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
