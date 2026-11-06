class MarkdownHeaderTextSplitter:
    def __init__(
        self, headers_to_split_on: list[tuple[str, str]], chunk_size: int = 500
    ):
        """
        :param headers_to_split_on: 例如 [("#", "Header 1"), ("##", "Header 2"), ...]
        :param chunk_size: 如果正文超过该长度，就继续切分
        """
        # 按照长度从大到小排序，保证 ## 不会被 # 提前匹配掉
        self.headers = sorted(headers_to_split_on, key=lambda x: -len(x[0]))
        self.chunk_size = chunk_size

    def _split_long_text(self, text: str) -> list[str]:
        """
        将超过 chunk_size 的文本切分成小块
        （这里用简单的按字符数切分，你也可以换成按句子、按换行切分）
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start = end
        return chunks

    def split_text(self, text: str) -> list[dict[str, str]]:
        """
        拆分 Markdown 文本
        :param text: Markdown 文本
        :return: [{'Header 1': 'Introduction', 'content': '...'}, ...]
        """
        lines = text.splitlines()
        results = []
        current_headers = {}
        buffer = []

        for line in lines:
            line_stripped = line.strip()
            matched = False

            for prefix, header_name in self.headers:
                if line_stripped.startswith(prefix + " "):  # 匹配标题
                    # 如果之前有内容缓冲，先保存
                    if buffer:
                        content = "\n".join(buffer).strip()
                        for chunk in self._split_long_text(content):
                            results.append({**current_headers, "content": chunk})
                        buffer = []
                    # 更新当前标题
                    current_headers[header_name] = line_stripped[len(prefix) :].strip()
                    # 如果是更高层级标题，清除低层级标题
                    prefix_level = len(prefix)
                    for pfx, hname in self.headers:
                        if len(pfx) > prefix_level and hname in current_headers:
                            del current_headers[hname]
                    matched = True
                    break

            if not matched:
                buffer.append(line)

        # 收尾
        if buffer:
            content = "\n".join(buffer).strip()
            for chunk in self._split_long_text(content):
                results.append({**current_headers, "content": chunk})

        return results
