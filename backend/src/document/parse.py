import asyncio
import hashlib
from io import BytesIO
import logging
from pathlib import Path
import re

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling_core.types.io import DocumentStream

from src.llm.factory import get_configured_llm
from src.prompt import llm_call

from config import rag_cfg


logger = logging.getLogger(__name__)


# CPU密集型任务，不需要async
def docling_to_markdown(
    document_stream: DocumentStream, output_path: str | Path, **kwargs
) -> str:
    """使用 Docling 将文件转换为 Markdown 格式并保存到指定路径。"""
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_picture_description = kwargs.get(
        "do_picture_description", False
    )
    pipeline_options.do_ocr = kwargs.get("do_ocr", False)
    pipeline_options.do_table_structure = kwargs.get("do_table_structure", True)
    pipeline_options.table_structure_options.do_cell_matching = kwargs.get(  # type: ignore
        "do_cell_matching", True
    )
    pipeline_options.do_formula_enrichment = True
    pipeline_options.accelerator_options = kwargs.get(
        "accelerator_options",
        AcceleratorOptions(num_threads=8, device=AcceleratorDevice.AUTO),
    )

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    conversion_result = converter.convert(document_stream)
    markdown_content = remove_line_numbers(
        conversion_result.document.export_to_markdown()
    )
    # conversion_result.document.save_as_markdown(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return markdown_content


class ParseResult:
    __slots__ = "title", "abstract", "keywords", "directory", "language"

    def __init__(
        self,
        title: str,
        abstract: str,
        keywords: list[str],
        markdown_title: list[str],
        language: str = "EN",
    ):
        self.title = title
        self.abstract = abstract
        self.keywords = keywords
        self.directory = markdown_title
        self.language = language


async def parse(file_path: str, output_path: str) -> ParseResult:
    if not file_path.endswith((".pdf", ".docx", ".doc", ".txt", ".md")):
        logger.warning(f"文件 {file_path} 不是支持的文件格式。")
        raise ValueError("Unsupported file format")

    with open(file_path, "rb") as f:
        data = f.read()

    # convert to markdown
    try:
        document_stream = DocumentStream(
            name=Path(file_path).name, stream=BytesIO(data)
        )

        markdown_content = await asyncio.to_thread(
            docling_to_markdown, document_stream, output_path, **rag_cfg["docling"]
        )
    except Exception as e:
        logger.error(f"文件转换失败: {file_path}", exc_info=e)
        raise RuntimeError(f"Markdown 转换失败: {file_path}") from e

    abstract_keywords, title, markdown_title, is_chinese = await asyncio.gather(
        extract_abstract_keywords(markdown_content),
        extract_title_from_markdown(markdown_content),
        extract_markdown_title(markdown_content),
        contains_chinese(markdown_content),
    )

    return ParseResult(
        title=title if title else "",
        abstract=abstract_keywords[0] if abstract_keywords else "",
        keywords=abstract_keywords[1] if abstract_keywords else [],
        markdown_title=markdown_title if markdown_title else [],
        language="ZH" if is_chinese else "EN",
    )


async def extract_abstract_keywords(markdown_content: str) -> tuple[str, list] | None:
    """提取文章摘要和关键词"""
    max_tokens = min(9000, len(markdown_content))
    if max_tokens == 0:
        return None
    llm = await get_configured_llm("rag")

    for start in range(0, max_tokens, 3000):
        text = markdown_content[start : min(start + 3000, max_tokens)]
        llm_response = await llm_call(
            prompt_name="extract_abstract", llm=llm, args={"text": text}
        )
        if llm_response is None:
            raise RuntimeError("LLM 调用失败，未获取响应。")

        if llm_response == "false":
            continue

        if "abstract" in llm_response and "keywords" in llm_response:
            return llm_response["abstract"], llm_response["keywords"]

    return None


async def extract_title_from_markdown(markdown_content: str) -> str | None:
    """提取文章标题"""

    max_tokens = min(9000, len(markdown_content))
    if max_tokens == 0:
        return None
    llm = await get_configured_llm("rag")

    for start in range(0, max_tokens, 3000):
        text = markdown_content[start : min(start + 3000, max_tokens)]
        llm_response = await llm_call(
            prompt_name="extract_title", llm=llm, args={"text": text}
        )
        if llm_response is None:
            raise RuntimeError("LLM 调用失败，未获取响应。")

        if llm_response == "false":
            continue

        if "title" in llm_response:
            return llm_response["title"]

    return None


async def extract_markdown_title(markdown_content: str) -> list[str] | None:
    """
    提取 Markdown 中的一级(#)和二级标题(##)，保留标题前缀。
    返回例如 ["# Title", "## Subtitle"]
    """
    # 捕获整行的 #/## 标题，不误匹配 ###
    title_pattern = re.compile(r"^(#{1,2}\s+.+)$", re.MULTILINE)

    matches = title_pattern.findall(markdown_content)

    if not matches:
        return None

    # 去掉行末多余空格
    return [m.rstrip() for m in matches]


async def contains_chinese(markdown_content: str, sample_size: int = 5000) -> bool:
    """快速检测文档是否包含中文，只检查前 sample_size 个字符, 如果中文字符超过100个则认为是中文文档"""
    pattern = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
    # return bool(pattern.search(markdown_content[:sample_size]))
    sample_text = markdown_content[:sample_size]
    chinese_chars = pattern.findall(sample_text)
    return len(chinese_chars) >= 100


def read_file_and_md5(filepath: str) -> tuple[bytes, str]:
    """
    一次读取文件内容，同时计算 MD5
    :return: (原始文件 bytes , MD5 哈希)
    """
    md5 = hashlib.md5()

    with open(filepath, "rb") as f:
        data = f.read()
        md5.update(data)

    return data, md5.hexdigest()


def remove_line_numbers(markdown_text: str) -> str:
    # 正则表达式：匹配行首的一个或多个数字，及其后的空格/制表符
    # 匹配模式: ^\d+\s*
    # ^ : 匹配行首
    # \d+ : 匹配一个或多个数字
    # \s* : 匹配零个或多个空格或制表符
    cleaned_text = re.sub(r"^\d+\s*", "", markdown_text, flags=re.MULTILINE)
    return cleaned_text
