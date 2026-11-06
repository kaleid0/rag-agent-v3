from langchain_core.documents import Document


from .MarkdownHeaderTextSplitter import MarkdownHeaderTextSplitter
from .MessagesTextSplitter import MessagesTextSplitter
from .LangchainTextSplitter import (
    CharacterTextSplitter,
    RecursiveTextSplitter,
)


def get_chunks(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    split_method: str = "hierarchical",  # 'hierarchical' or 'recursive'
    metadata: dict | None = None,
) -> list[Document]:

    # 切片处理
    chunks = _chunking(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        split_method=split_method,
    )
    chunks = _build_documents(chunks, metadata=metadata)

    return chunks


def _chunking(
    text: str,
    chunk_size: int,
    chunk_overlap: int = 0,
    split_method: str = "character",
    **kwargs,
) -> list[dict[str, str]]:
    """
    文档分块处理, 保存片段

    output: list[dict] [{'Header 1': 'Introduction', 'content': '...'}, ...]
    """
    if split_method == "character":
        text_splitter = CharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        # -> list[dict] [{'content': '...'}, ...]

    elif split_method == "recursive":
        text_splitter = RecursiveTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=kwargs.get("separators"),
        )
        # -> list[dict] [{'content': '...'}, ...]

    elif split_method == "hierarchical":
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        text_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            chunk_size=chunk_size,
        )
        # -> list[dict] [{'Header 1': 'Introduction', 'content': '...'}, ...]

    else:
        raise ValueError(f"Unknown split_method: {split_method}")

    text_list = text_splitter.split_text(text)

    return text_list


def _build_documents(
    chunks: list[dict], metadata: dict | None = None
) -> list[Document]:
    """
    添加id元数据
    """
    documents = [
        Document(
            page_content=chunk.get("content", ""),
            metadata={
                "header": chunk.get("Header 3")
                or chunk.get("Header 2")
                or chunk.get("Header 1")
                or "No Header",
                # "document_title": document_title if document_title else "unknown_title",
                # "collection_id": str(record_id) if record_id else "unknown_record",
                "num_chunks": len(chunks),
            }
            | (metadata or {}),
            id=f"{i}",
        )
        for i, chunk in enumerate(chunks)
    ]

    return documents


def get_chunks_from_messages(
    messages: list[dict[str, str]],
    max_chunk_size: int = 500,
    metadata: dict | None = None,
) -> list[Document]:

    text_splitter = MessagesTextSplitter(max_chunk_size=max_chunk_size)
    chunks = text_splitter.split_text(messages)
    chunks = _build_documents(chunks, metadata=metadata)

    return chunks
