import os
from pathlib import Path

from pydantic_settings import BaseSettings

# 应用目录名：用户级配置与数据目录共用，集中定义便于整体改名
APP_DIR_NAME = "ai-dailyreport"


def _user_config_dir() -> Path:
    """用户级配置目录：优先 XDG_CONFIG_HOME，缺省 ~/.config。"""
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_DIR_NAME


USER_CONFIG_DIR = _user_config_dir()
USER_ENV_FILE = USER_CONFIG_DIR / ".env"


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.7

    # 语义检索（embedding）配置，使用硅基流动的 OpenAI 兼容接口
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-large-zh-v1.5"

    # 数据目录：留空使用默认（源码运行→项目 data/；pip 安装→用户级目录），可自定义
    data_dir: str = ""

    class Config:
        # 用户级配置优先（/config 命令行修改的配置在任意目录生效），
        # 项目 .env 作为回退兜底（本地开发可预置默认值）
        env_file = [".env", str(USER_ENV_FILE)]
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
