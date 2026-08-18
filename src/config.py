from pathlib import Path

from pydantic_settings import BaseSettings

# 用户级配置目录：pip 安装后在任意目录运行也能找到配置
USER_CONFIG_DIR = Path.home() / ".config" / "ai-dailyreport"
USER_ENV_FILE = USER_CONFIG_DIR / ".env"


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.7

    class Config:
        # 用户目录配置为默认，当前目录 .env 可覆盖（本地开发场景）
        env_file = [str(USER_ENV_FILE), ".env"]
        env_file_encoding = "utf-8"


def save_env_file(**values: str) -> Path:
    """将配置项合并写入用户级 .env，已存在的键更新、新键追加。"""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if USER_ENV_FILE.exists():
        for line in USER_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                existing[key.strip()] = val.strip()
    existing.update(values)
    USER_ENV_FILE.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    return USER_ENV_FILE
