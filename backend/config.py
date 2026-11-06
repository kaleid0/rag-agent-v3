import tomllib
from pathlib import Path

config_path = Path(__file__).with_name("pyproject.toml")
if not config_path.is_file():
    config_path = Path("pyproject.toml")

with config_path.open("rb") as config_file:
    cfg = tomllib.load(config_file)

mongo_cfg = cfg["tool"]["mongo"]
chroma_cfg = cfg["tool"]["chroma"]

rag_cfg = cfg["tool"]["rag"]

memory_cfg = cfg["tool"]["memory"]

dialog_cfg = cfg["tool"]["dialog"]
