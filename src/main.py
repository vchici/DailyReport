import asyncio
import readline  # 启用 GNU readline 行编辑，修复 CJK 回撤输入错乱
import time
from datetime import datetime

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Settings
from .agent.orchestrator import DailyReportAgent


console = Console()


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


def _animate_intro() -> None:
    """进场动画：日期数字跳动 → 平滑过渡为「日期标题 + 命令面板」主界面。"""

    now = datetime.now()

    rows = [
        ("/plan", "记录待办事项（多行，以单独 . 结束）", None),
        ("/done", "记录已完成事项", None),
        ("/chat", "自由对话，检索历史 + 联网信息", None),
        ("/report", "生成本日完整日报", None),
        ("/status", "查看今日概况", None),
        ("/help", "显示帮助  |  /exit 退出", None),
        ("", "", None),
        ("→", "直接输入自然语言，AI 会自动识别意图", "italic"),
    ]

    def _date(day: int) -> Text:
        label = f"{now.month:02d}/{day:02d}/{now.year % 100:02d}"
        left_pad = max(0, (console.width - len(label)) // 2)
        return Text(" " * left_pad + label, style="bold yellow")

    def _panel(visible: int, border_style: str = "bold cyan") -> Align:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", width=10)
        table.add_column(style="dim")
        for i, (cmd, desc, style) in enumerate(rows):
            if i < visible:
                if style:
                    table.add_row(cmd, desc, style=style)
                else:
                    table.add_row(cmd, desc)
            else:
                table.add_row("", "")  # 占位，保持面板高度稳定
        panel = Panel(
            table,
            title="[bold]Daily Report[/bold]",
            title_align="center",
            subtitle="[dim]AI 驱动的个人日报助手[/dim]",
            border_style=border_style,
            padding=(1, 2),
        )
        return Align.center(panel)

    with Live(console=console, refresh_per_second=30, auto_refresh=False) as live:
        # 1) 日期数字跳动
        for d in range(1, now.day + 1):
            live.update(_date(d))
            live.refresh()
            time.sleep(0.05)

        # 2) 平滑过渡：命令面板外框在日期下方淡入
        for border in ("dim cyan", "cyan"):
            live.update(Group(_date(now.day), _panel(0, border)))
            live.refresh()
            time.sleep(0.09)

        # 3) 内容逐行揭示，日期保留为标题栏
        for visible in range(1, len(rows) + 1):
            live.update(Group(_date(now.day), _panel(visible)))
            live.refresh()
            time.sleep(0.05)

    console.print()


async def _run() -> None:
    settings = Settings()
    agent = DailyReportAgent(settings)

    _animate_intro()

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
                from .storage import append_plan_suggestion
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
                from .storage import save_daily_report
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
            # 非 / 开头 → 自然语言输入，自动识别意图
            print(f"\n⏳ 正在理解...\n")
            result = await agent.auto_dispatch(cmd_line)
            print(result)
            print()


def main() -> None:
    """同步入口，供 console script 调用。"""
    asyncio.run(_run())
