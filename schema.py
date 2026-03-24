from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Sequence


class SchemaError(ValueError):
    pass


@dataclass
class VocabularyCardData:
    word: str
    phonetic: str
    part_of_speech: str
    definition: str
    translation: str
    example_sentence: str
    example_translation: str
    synonyms: List[str] = field(default_factory=list)
    antonyms: List[str] = field(default_factory=list)
    collocations: List[str] = field(default_factory=list)
    memory_tip: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def _collapse(value: str) -> str:
    return " ".join(value.strip().split())


def _to_string(value: Any, name: str) -> str:
    if value is None:
        raise SchemaError(f"Missing required field: {name}")
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        if not text:
            raise SchemaError(f"Empty required field: {name}")
        return _collapse(text)
    raise SchemaError(f"Field {name} must be a string")


def _to_optional_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return _collapse(str(value))
    raise SchemaError("Optional string fields must be strings")


def _to_list(value: Any, name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise SchemaError(f"Field {name} must be a list of strings")
    items: List[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            items.append(_collapse(text))
    return items


def extract_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    match = _CODE_FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise SchemaError("LLM response did not contain a JSON object")
    return text[first : last + 1]


def parse_vocabulary_card(raw_text: str) -> VocabularyCardData:
    json_text = extract_json_text(raw_text)
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"Invalid JSON from LLM: {exc}") from exc
    if not isinstance(payload, dict):
        raise SchemaError("LLM response must be a JSON object")

    return VocabularyCardData(
        word=_to_string(payload.get("word"), "word"),
        phonetic=_to_optional_string(payload.get("phonetic", "")),
        part_of_speech=_to_optional_string(payload.get("part_of_speech", "")),
        definition=_to_string(payload.get("definition"), "definition"),
        translation=_to_string(payload.get("translation"), "translation"),
        example_sentence=_to_string(payload.get("example_sentence"), "example_sentence"),
        example_translation=_to_string(payload.get("example_translation"), "example_translation"),
        synonyms=_to_list(payload.get("synonyms"), "synonyms"),
        antonyms=_to_list(payload.get("antonyms"), "antonyms"),
        collocations=_to_list(payload.get("collocations"), "collocations"),
        memory_tip=_collapse(str(payload.get("memory_tip", "")).strip()) if payload.get("memory_tip") else "",
    )
