# src/prompt/register.py
from pathlib import Path
import pkgutil
import importlib
import logging

logger = logging.getLogger(__name__)


def load_all_prompts():
    prompts_dir = Path(__file__).parent

    # 遍历 prompt_template 下的子包
    for module in pkgutil.iter_modules([str(prompts_dir)]):
        # 构造 register.py 的完整模块路径
        submodule_name = f"src.prompt.{module.name}.register"
        logger.debug(f"Loading prompt module: {submodule_name}")
        try:
            importlib.import_module(submodule_name)
        except ModuleNotFoundError as e:
            if "register" in str(e):
                # 某个子目录没有 register.py，忽略
                continue
            else:
                # 其他 ModuleNotFoundError 不忽略
                raise
