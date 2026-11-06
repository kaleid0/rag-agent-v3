class MessagesTextSplitter:
    def __init__(
        self,
        max_chunk_size: int = 500,
    ):
        self.max_chunk_size = max_chunk_size

    def split_text(self, messages: list[dict[str, str]]):
        result = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # 按 max_len 切分 content
            parts = [content[i : i + self.max_chunk_size] for i in range(0, len(content), self.max_chunk_size)]

            # 为每段创建一条新消息
            for part in parts:
                result.append({"Header 1": role, "content": part})

        return result
