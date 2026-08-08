from .state import Event, ReportOutline


async def plan_report(events: list[Event]) -> ReportOutline:
    """根据事件列表规划日报结构。"""
    if not events:
        return ReportOutline(summary="今日无记录的工作事件。")

    high_priority = [e for e in events if e.priority == 1]
    normal_priority = [e for e in events if e.priority == 0]

    # 生成摘要
    key_titles = [e.title for e in (high_priority or events)]
    summary = f"今日完成{len(events)}项工作，重点包括：{'、'.join(key_titles[:3])}"

    # 构建段落列表：高优先级在前
    sections = []
    for e in high_priority + normal_priority:
        sections.append(
            {
                "type": e.type.value,
                "title": e.title,
                "detail": e.detail,
                "priority": e.priority,
            }
        )

    return ReportOutline(summary=summary, sections=sections)
