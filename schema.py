from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Sequence


class SchemaError(ValueError):
    pass


@dataclass
class MeaningEntry:
    part_of_speech: str
    definition: str
    example_sentence: str = ""
    meaning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CollocationEntry:
    phrase: str
    gloss: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtraExampleEntry:
    sentence: str
    meaning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VocabularyCardData:
    word: str
    ipa: str
    base_form: str
    part_of_speech: str
    register: str
    frequency: str
    meanings: List[MeaningEntry] = field(default_factory=list)
    collocations: List[CollocationEntry] = field(default_factory=list)
    extra_examples: List[ExtraExampleEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "ipa": self.ipa,
            "base_form": self.base_form,
            "part_of_speech": self.part_of_speech,
            "register": self.register,
            "frequency": self.frequency,
            "meanings": [item.to_dict() for item in self.meanings],
            "collocations": [item.to_dict() for item in self.collocations],
            "extra_examples": [item.to_dict() for item in self.extra_examples],
        }


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


def _to_list(value: Any, name: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise SchemaError(f"Field {name} must be a list")
    return list(value)


def _parse_meaning(entry: Any) -> MeaningEntry:
    if isinstance(entry, str):
        text = _collapse(entry)
        if not text:
            raise SchemaError("Meaning definition cannot be empty")
        return MeaningEntry(part_of_speech="", definition=text)
    if not isinstance(entry, dict):
        raise SchemaError("Each meaning must be an object")
    definition = _to_string(entry.get("definition"), "meanings[].definition")
    return MeaningEntry(
        part_of_speech=_to_optional_string(entry.get("part_of_speech")),
        definition=definition,
        example_sentence=_to_optional_string(entry.get("example_sentence")),
        meaning=_to_optional_string(entry.get("meaning")),
    )


def _parse_collocation(entry: Any) -> CollocationEntry:
    if isinstance(entry, str):
        text = _collapse(entry)
        if not text:
            raise SchemaError("Collocation phrase cannot be empty")
        return CollocationEntry(phrase=text)
    if not isinstance(entry, dict):
        raise SchemaError("Each collocation must be an object")
    phrase = _to_string(entry.get("phrase"), "collocations[].phrase")
    return CollocationEntry(phrase=phrase, gloss=_to_optional_string(entry.get("gloss")))


def _parse_extra_example(entry: Any) -> ExtraExampleEntry:
    if isinstance(entry, str):
        text = _collapse(entry)
        if not text:
            raise SchemaError("Example sentence cannot be empty")
        return ExtraExampleEntry(sentence=text)
    if not isinstance(entry, dict):
        raise SchemaError("Each extra example must be an object")
    sentence = _to_string(entry.get("sentence"), "extra_examples[].sentence")
    return ExtraExampleEntry(sentence=sentence, meaning=_to_optional_string(entry.get("meaning")))


def _fallback_meanings(payload: Dict[str, Any], part_of_speech: str) -> List[MeaningEntry]:
    definition = _to_optional_string(payload.get("definition"))
    if not definition:
        return []
    return [
        MeaningEntry(
            part_of_speech=part_of_speech,
            definition=definition,
            example_sentence=_to_optional_string(payload.get("example_sentence")),
            meaning=_to_optional_string(payload.get("meaning")) or _to_optional_string(payload.get("example_translation")),
        )
    ]


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

    word = _to_string(payload.get("word"), "word")
    ipa = _to_optional_string(payload.get("ipa") or payload.get("phonetic"))
    base_form = _to_optional_string(payload.get("base_form")) or word
    part_of_speech = _to_optional_string(payload.get("part_of_speech"))
    register = _to_optional_string(payload.get("register")) or "neutral"
    frequency = _to_optional_string(payload.get("frequency")) or "common"

    meanings_raw = payload.get("meanings")
    meanings: List[MeaningEntry]
    if meanings_raw is None:
        meanings = _fallback_meanings(payload, part_of_speech)
    else:
        meanings = [_parse_meaning(item) for item in _to_list(meanings_raw, "meanings")]

    collocations_raw = payload.get("collocations")
    collocations = [_parse_collocation(item) for item in _to_list(collocations_raw, "collocations")]

    extra_examples_raw = payload.get("extra_examples")
    if extra_examples_raw is None:
        extra_examples = []
        if payload.get("example_sentence"):
            extra_examples.append(
                ExtraExampleEntry(
                    sentence=_to_optional_string(payload.get("example_sentence")),
                    meaning=_to_optional_string(payload.get("example_translation")) or _to_optional_string(payload.get("meaning")),
                )
            )
    else:
        extra_examples = [_parse_extra_example(item) for item in _to_list(extra_examples_raw, "extra_examples")]

    return VocabularyCardData(
        word=word,
        ipa=ipa,
        base_form=base_form,
        part_of_speech=part_of_speech,
        register=register,
        frequency=frequency,
        meanings=meanings,
        collocations=collocations,
        extra_examples=extra_examples,
    )
