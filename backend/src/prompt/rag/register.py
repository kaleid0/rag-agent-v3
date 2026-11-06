"""Register RAG prompts from their TOML configuration."""

import json
from pathlib import Path

from src.prompt.auto_register import (
    register_custom_input_builder,
    register_prompts_from_toml,
)
from src.prompt.get_prompt import get_prompt


def query_route_input_builder(args: dict) -> str:
    prompt = get_prompt("query_route", "rag")
    return prompt.format(
        collections=json.dumps(args["collections"], ensure_ascii=False),
        question=args["question"],
    )


register_custom_input_builder("query_route", query_route_input_builder)
registered_prompts = register_prompts_from_toml(Path(__file__).with_name("prompts.toml"))
