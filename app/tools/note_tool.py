import json 
import re
from pathlib import Path
from typing import Any

def _ensure_parents(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def save_json(path: Path, payload: Any) -> None:
    _ensure_parents(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def save_markdown(path: Path, content: str) -> None:
    _ensure_parents(path)
    path.write_text(content, encoding="utf-8")