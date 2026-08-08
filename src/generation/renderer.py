from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def render_report(report_content: str, template_name: str = "default.md") -> str:
    """使用 Jinja2 模板渲染日报最终输出。"""
    template_dir = Path(__file__).parent.parent.parent / "data" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(template_name)
    return template.render(content=report_content)
