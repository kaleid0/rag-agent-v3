"""
Dialog Prompts Registration
使用TOML配置文件自动注册prompts
"""

from pathlib import Path
from src.prompt.auto_register import register_prompts_from_toml


# 从同目录下的prompts.toml文件自动注册所有prompts
current_dir = Path(__file__).parent
toml_path = current_dir / "prompts.toml"

registered_prompts = register_prompts_from_toml(toml_path)
