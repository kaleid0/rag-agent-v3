"""
Prompt自动注册工具
从TOML配置文件中读取prompt定义并自动注册到PROMPT_REGISTRY
"""

import json
from pathlib import Path
import tomllib
from typing import Callable

from src.prompt.PromptConfig import PromptConfig, register_prompt
from src.prompt.get_prompt import get_prompt


# 输出解析器映射
OUTPUT_PARSERS = {
    "plain": lambda response: response,
    "json": json.loads,
    "strip_quotes": lambda response: response.strip().strip('"'),
    "strip": lambda response: response.strip(),
}


INPUT_BUILDERS = {}


def get_output_parser(parser_type: str) -> Callable:
    """
    获取输出解析器
    """
    if parser_type not in OUTPUT_PARSERS:
        raise ValueError(
            f"Unknown output parser: {parser_type}. "
            f"Available: {list(OUTPUT_PARSERS.keys())}"
        )
    return OUTPUT_PARSERS[parser_type]


def get_plain_input_builder(
    template_name: str, module_name: str, input_params: dict
) -> Callable:
    """
    根据配置创建input_builder函数

    Args:
        template: prompt模板名称
        category: prompt分类
        input_params: 参数映射字典，格式: {template_var: args_key}

    Returns:
        input_builder函数
    """

    def input_builder(args: dict) -> str:
        # 从args中提取参数并转换为字符串
        format_kwargs = {
            template_var: str(args[args_key])
            for template_var, args_key in input_params.items()
        }
        # 获取模板并格式化
        prompt_template = get_prompt(template_name, module_name)
        return prompt_template.format(**format_kwargs)

    return input_builder


def register_custom_input_builder(name: str, builder_func: Callable) -> None:
    """
    注册自定义的input_builder函数
    """
    INPUT_BUILDERS[name] = builder_func


def get_input_builder(
    config: dict, prompt_name: str, template: str, category: str
) -> Callable:
    """
    根据配置获取或创建input_builder

    Args:
        config: prompt配置字典
        prompt_name: prompt名称
        template: 模板名称
        category: 分类名称

    Returns:
        input_builder函数
    """
    # 如果指定了custom_input_builder，使用自定义函数
    custom_builder_name = config.get("custom_input_builder")
    if custom_builder_name:
        if custom_builder_name not in INPUT_BUILDERS:
            raise ValueError(
                f"Custom input builder '{custom_builder_name}' not found for prompt '{prompt_name}'. "
                f"Available: {list(INPUT_BUILDERS.keys())}"
            )
        return INPUT_BUILDERS[custom_builder_name]

    # 否则使用标准的input_params方式
    input_params = config.get("input_params", {})
    return get_plain_input_builder(template, category, input_params)


def register_prompts_from_toml(toml_path: str | Path) -> list[str]:
    """
    从TOML配置文件中读取并注册所有prompts

    Args:
        toml_path: TOML配置文件路径

    Returns:
        已注册的prompt名称列表
    """
    toml_path = Path(toml_path)

    if not toml_path.exists():
        raise FileNotFoundError(f"TOML config file not found: {toml_path}")

    # 读取TOML配置
    with open(toml_path, "rb") as f:
        config = tomllib.load(f)

    registered_names = []

    # 遍历配置中的每个prompt
    for prompt_name, prompt_config in config.items():
        # 提取配置项
        template = prompt_config.get("template", prompt_name)
        category = prompt_config.get("category", "dialog")
        output_parser_type = prompt_config.get("output_parser", "plain")
        llm_args = prompt_config.get("llm_args", {})

        # 获取input_builder（支持自定义或标准方式）
        input_builder = get_input_builder(
            prompt_config, prompt_name, template, category
        )

        # 创建PromptConfig并注册
        prompt_cfg = PromptConfig(
            name=prompt_name,
            input_builder=input_builder,
            output_parser=get_output_parser(output_parser_type),
            llm_args=llm_args,
        )

        register_prompt(prompt_cfg)
        registered_names.append(prompt_name)

    return registered_names


def auto_register_from_directory(directory: str | Path) -> dict[str, list[str]]:
    """
    自动扫描目录中的所有prompts.toml文件并注册

    Args:
        directory: 要扫描的目录路径

    Returns:
        字典，key为toml文件路径，value为该文件中注册的prompt名称列表
    """
    directory = Path(directory)
    results = {}

    # 递归查找所有prompts.toml文件
    for toml_file in directory.rglob("prompts.toml"):
        try:
            registered = register_prompts_from_toml(toml_file)
            results[str(toml_file)] = registered
        except Exception as e:
            print(f"Warning: Failed to register prompts from {toml_file}: {e}")

    return results
