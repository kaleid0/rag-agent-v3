from typing import Protocol


class TextSplitterProtocol(Protocol):
    def split_text(self, text: str) -> list[dict[str, str]]: ...
