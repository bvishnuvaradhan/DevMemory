"""Curated troubleshooting knowledge base loader and accessors for DevMemory.

Loads and validates pre-populated knowledge entries against the
Pydantic KnowledgeBaseItem schema.
"""

import json
from pathlib import Path
from typing import List, Optional
from pydantic import ValidationError

from ai_engine.schemas import KnowledgeBaseItem

_DEFAULT_SEED_FILE = Path(__file__).parent / "seed_data.json"
_CACHED_KNOWLEDGE: Optional[List[KnowledgeBaseItem]] = None


def load_knowledge_base(file_path: Optional[Path | str] = None) -> List[KnowledgeBaseItem]:
    """Load and strictly validate knowledge base entries from a JSON file.
    
    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If JSON is malformed or any item fails Pydantic validation.
    """
    path = Path(file_path) if file_path else _DEFAULT_SEED_FILE
    if not path.is_file():
        raise FileNotFoundError(f"Knowledge base file not found at: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as err:
        raise ValueError(f"Malformed JSON in knowledge base file '{path}': {err}") from err

    if not isinstance(raw_data, list):
        raise ValueError(f"Knowledge base root must be a list of items, got {type(raw_data).__name__}")

    items: List[KnowledgeBaseItem] = []
    for idx, entry in enumerate(raw_data):
        if not isinstance(entry, dict):
            raise ValueError(f"Knowledge base item at index {idx} must be a dictionary, got {type(entry).__name__}")
        try:
            item = KnowledgeBaseItem.model_validate(entry)
            items.append(item)
        except ValidationError as val_err:
            entry_id = entry.get("kb_id", f"index_{idx}")
            raise ValueError(
                f"Validation error in knowledge base entry '{entry_id}': {val_err}"
            ) from val_err

    return items


def get_default_knowledge_base() -> List[KnowledgeBaseItem]:
    """Retrieve the cached default curated knowledge base items."""
    global _CACHED_KNOWLEDGE
    if _CACHED_KNOWLEDGE is None:
        _CACHED_KNOWLEDGE = load_knowledge_base(_DEFAULT_SEED_FILE)
    return _CACHED_KNOWLEDGE


__all__ = [
    "load_knowledge_base",
    "get_default_knowledge_base",
]
