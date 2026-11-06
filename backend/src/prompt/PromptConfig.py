from dataclasses import dataclass
from typing import Callable

PROMPT_REGISTRY = {}


@dataclass
class PromptConfig:
    name: str
    input_builder: Callable
    output_parser: Callable
    llm_args: dict


def register_prompt(config: PromptConfig):
    if config.name in PROMPT_REGISTRY:
        raise ValueError(f"Duplicate prompt registered: {config.name}")
    PROMPT_REGISTRY[config.name] = config


# 示例
"""
register_prompt(
    PromptConfig(
        name="short_memory_summary",
        input_builder=lambda args: get_prompt("short_term_memory_summary").format(
            messages=str(args["messages"])
        ),
        output_parser=json.loads,
        input_args={"messages": list},
        llm_args={"format": "json", "temperature": 0, "max_tokens": 1000},
    )
)
"""
