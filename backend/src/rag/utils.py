from langchain_core.documents import Document


def query_for_language(query: dict | str, language: str) -> str:
    if isinstance(query, str):
        return query
    return query.get(language) or query.get("EN") or query.get("ZH") or ""


def group_by_collection(documents: list[Document]) -> dict[str, list[Document]]:
    groups: dict[str, list[Document]] = {}
    for doc in documents:
        key = doc.metadata.get("collection_id") or doc.metadata.get("record_id")
        if not key:
            key = doc.metadata.get("document_title") or "unknown"
        groups.setdefault(key, []).append(doc)
    return groups


def remove_duplicates(documents: list[Document]) -> list[Document]:
    seen = set()
    unique = []
    for doc in documents:
        source_id = (
            doc.metadata.get("collection_id")
            or doc.metadata.get("record_id")
            or doc.metadata.get("session_id")
        )
        if source_id is None or doc.id is None:
            unique.append(doc)
            continue
        key = (source_id, doc.id)
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


def organize_context(documents: dict[str, list[Document]]) -> str:
    """将 Document 列表组织成纯文本，并合并相邻同 header 的片段。"""

    organized_texts = []

    for record_id, docs in documents.items():
        if not docs:
            organized_texts.append(f"=== 文档（ID: {record_id}）无内容 ===\n")
            continue

        record_title = docs[0].metadata.get("document_title", "未知文档")
        organized_texts.append(f"=== 文档标题: {record_title} ===")

        # 1. 合并相邻 header 相同的片段
        merged_sections = []  # list[(header, content)]

        prev_header = None
        buffer_content = []

        for doc in docs:
            header = doc.metadata.get("header") or "未命名章节"
            content = doc.page_content.strip()

            if header == prev_header:
                # 和上一个章节同名 → 累积
                buffer_content.append(content)
            else:
                # 若 header 改变，把前面累积的存进结果
                if prev_header is not None:
                    merged_sections.append((prev_header, "\n".join(buffer_content)))
                # 开始新的 buffer
                prev_header = header
                buffer_content = [content]

        # 别忘记最后一个
        if prev_header is not None:
            merged_sections.append((prev_header, "\n".join(buffer_content)))

        # 2. 输出文本
        for header, content in merged_sections:
            organized_texts.append(f"\n--- 章节: {header} ---\n{content}")

        organized_texts.append("\n")

    return "\n".join(organized_texts).strip()
