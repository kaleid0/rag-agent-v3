from openai import APIError

from .PromptConfig import PROMPT_REGISTRY
from src.llm import BaseChatAdapter


async def llm_call(prompt_name: str, llm: BaseChatAdapter, args: dict):
    if prompt_name not in PROMPT_REGISTRY:
        raise ValueError(f"Unknown prompt: {prompt_name}")

    cfg = PROMPT_REGISTRY[prompt_name]

    # 1. 构建 prompt
    prompt_text = cfg.input_builder(args)

    # 2. 调用 LLM
    try:
        response = await llm.async_call(prompt_text, **cfg.llm_args)
    except APIError:
        raise RuntimeError("模型服务请求失败") from None
    if not response:
        raise RuntimeError("LLM 调用失败")

    # 3. 解析输出
    try:
        output = cfg.output_parser(response)
    except Exception as e:
        raise RuntimeError(f"LLM 输出解析失败: {str(e)}") from e

    return output
    # return cfg.output_parser(response)


async def llm_chat_stream(
    prompt_name: str, llm: BaseChatAdapter, messages: list[dict[str, str]], args: dict
):
    if prompt_name not in PROMPT_REGISTRY:
        raise ValueError(f"Unknown prompt: {prompt_name}")

    cfg = PROMPT_REGISTRY[prompt_name]

    # 1. 构建 prompt
    prompt_text = cfg.input_builder(args)

    # 2. 调用 LLM 流式接口
    return llm.async_stream_chat(
        messages + [{"role": "user", "content": prompt_text}],
        **cfg.llm_args,
    )

