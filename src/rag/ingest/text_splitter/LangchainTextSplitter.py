from langchain_text_splitters import (
    CharacterTextSplitter as CTSplitter,
    RecursiveCharacterTextSplitter as RCTSplitter,
)


class RecursiveTextSplitter:
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
    ):
        self.splitter = RCTSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=separators
        )

    def split_text(self, text: str) -> list[dict[str, str]]:
        splitted_texts = self.splitter.split_text(text)
        return [{"content": t} for t in splitted_texts]


class CharacterTextSplitter:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.splitter = CTSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def split_text(self, text: str) -> list[dict[str, str]]:
        splitted_texts = self.splitter.split_text(text)
        return [{"content": t} for t in splitted_texts]
