import asyncio
import time
from datetime import datetime

# readline 仅 Unix 可用，Windows 下跳过（CJK 回撤问题由 pyreadline3 或终端自行处理）
try:
    import readline  # noqa: F401
except ImportError:
    readline = None

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
  /edit          修改已记录的事项（全部记录，分页选择）
  /delete        删除已记录的事项（全部记录，分页选择）
  /chat <内容>   自由对话，Agent 会检索历史记录和联网信息回答
  /report        生成本日完整日报
  /status        查看今日概况
  /help          显示此帮助
  /exit          退出"""


def read_multiline(first_line: str = "", prompt: str = "  ") -> str:
    """读取多行输入，以单独的 . 行结束。"""
    lines: list[str] = []
    if first_line:
        lines.append(first_line)
    while True:
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == ".":
            break
        lines.append(line)
    return "\n".join(lines)


PAGE_SIZE = 10


def _print_entries_page(entries: list[tuple[str, dict]], start: int, end: int, page: int, total_pages: int, title: str) -> None:
    table = Table(title=f"{title}（第 {page + 1}/{total_pages} 页）", show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    table.add_column("#", style="bold", width=4)
    table.add_column("日期", width=12)
    table.add_column("时间", style="dim", width=8)
    table.add_column("状态", width=8)
    table.add_column("内容", style="dim")
    for i in range(start, end):
        date_str, entry = entries[i]
        status = "待办" if entry.get("status") == "todo" else "已完成"
        raw = (entry.get("raw_input") or "").replace("\n", " ")[:40]
        table.add_row(str(i - start + 1), date_str, entry.get("time", ""), status, raw)
    console.print(table)


def _browse_entries(
    entries: list[tuple[str, dict]],
    title: str = "全部记录",
    page: int = 0,
) -> tuple[int | None, int]:
    """分页浏览条目，返回 (选中的全局索引, 当前页码)；取消时索引为 None。"""
    if not entries:
        print("暂无记录。\n")
        return None, page

    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
    while True:
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(entries))
        _print_entries_page(entries, start, end, page, total_pages, title)

        try:
            choice = input("输入编号选择，n 下一页，p 上一页，g 页码 跳转，q 退出: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None, page

        if choice in ("q", ""):
            return None, page
        if choice == "n":
            if page < total_pages - 1:
                page += 1
            else:
                print("已是最后一页。")
            continue
        if choice == "p":
            if page > 0:
                page -= 1
            else:
                print("已是第一页。")
            continue
        if choice.startswith("g"):
            spec = choice[1:].strip()
            if spec.isdigit():
                target = int(spec)
                if 1 <= target <= total_pages:
                    page = target - 1
                else:
                    print(f"页码需在 1-{total_pages} 之间。")
            else:
                print("输入无效，请重新输入。")
            continue
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= (end - start):
                return start + n - 1, page
        print("输入无效，请重新输入。")


async def _edit_entry(agent: DailyReportAgent) -> None:
    """交互式修改已记录的事项（全部记录，分页选择），输入 q 退出。"""
    page = 0
    while True:
        entries = agent.list_all_entries()
        global_index, page = _browse_entries(entries, title="选择要修改的记录", page=page)
        if global_index is None:
            return

        date_str, entry = entries[global_index]
        status = "待办" if entry.get("status") == "todo" else "已完成"
        print(f"\n当前内容（{date_str} {status}，{entry.get('time', '')}）：\n{entry.get('raw_input', '')}\n")
        print("请输入新的完整内容（多行输入，单独一行 . 结束；直接输入 . 则取消修改）：")
        new_content = read_multiline(prompt="  新内容 > ").strip()
        if not new_content:
            print("已取消修改。\n")
            continue

        print("\n⏳ 正在更新...\n")
        result = await agent.edit_entry(date_str, entry["_index"], new_content)
        print(result)
        print()


def _delete_entry(agent: DailyReportAgent) -> None:
    """交互式删除已记录的事项（全部记录，分页选择）。"""
    entries = agent.list_all_entries()
    global_index, _ = _browse_entries(entries, title="选择要删除的记录")
    if global_index is None:
        return

    date_str, entry = entries[global_index]
    status = "待办" if entry.get("status") == "todo" else "已完成"
    print(f"\n确认删除（{date_str} {status}，{entry.get('time', '')}）：\n{entry.get('raw_input', '')}\n")
    try:
        confirm = input("确认删除？(y/n，直接回车取消): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = "n"
    if confirm not in ("y", "yes"):
        print("已取消删除。\n")
        return

    result = agent.remove_entry(date_str, entry["_index"])
    print(result)
    print()


def _animate_intro() -> None:
    """进场动画：日期数字跳动 → 平滑过渡为「日期标题 + 命令面板」主界面。"""

    now = datetime.now()

    rows = [
        ("/plan", "记录待办事项（多行，以单独 . 结束）", None),
        ("/done", "记录已完成事项", None),
        ("/edit", "修改已记录的事项", None),
        ("/delete", "删除已记录的事项", None),
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

        elif cmd_line.startswith("/edit"):
            await _edit_entry(agent)

        elif cmd_line.startswith(("/delete", "/del")):
            _delete_entry(agent)

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
