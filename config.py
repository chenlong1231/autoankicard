from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
STATE_PATH = PROJECT_ROOT / ".autoankicard_state.json"
HISTORY_PATH = PROJECT_ROOT / ".autoankicard_history.json"
LOG_PATH = PROJECT_ROOT / ".autoankicard.log"


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: Optional[str], default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def load_env_file(path: Path = ENV_PATH) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class FieldMap:
    front: str = "Front"
    back: str = "Back"
    word: str = "Word"
    phonetic: str = "Phonetic"
    part_of_speech: str = "PartOfSpeech"
    definition: str = "Definition"
    translation: str = "Translation"
    example_sentence: str = "ExampleSentence"
    example_translation: str = "ExampleTranslation"
    synonyms: str = "Synonyms"
    antonyms: str = "Antonyms"
    collocations: str = "Collocations"
    memory_tip: str = "MemoryTip"

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "FieldMap":
        data = data or {}
        return cls(
            front=str(data.get("front", cls.front)),
            back=str(data.get("back", cls.back)),
            word=str(data.get("word", cls.word)),
            phonetic=str(data.get("phonetic", cls.phonetic)),
            part_of_speech=str(data.get("part_of_speech", cls.part_of_speech)),
            definition=str(data.get("definition", cls.definition)),
            translation=str(data.get("translation", cls.translation)),
            example_sentence=str(data.get("example_sentence", cls.example_sentence)),
            example_translation=str(data.get("example_translation", cls.example_translation)),
            synonyms=str(data.get("synonyms", cls.synonyms)),
            antonyms=str(data.get("antonyms", cls.antonyms)),
            collocations=str(data.get("collocations", cls.collocations)),
            memory_tip=str(data.get("memory_tip", cls.memory_tip)),
        )


@dataclass
class AppSettings:
    api_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "deepseek-ai/DeepSeek-V3.2"
    default_deck: str = "Default"
    note_model_name: str = "Basic"
    template_preset: str = "classic"
    skip_duplicates: bool = True
    tags: str = ""
    timeout_seconds: float = 60.0
    retry_count: int = 2
    retry_delay_seconds: float = 1.5
    field_map: FieldMap = field(default_factory=FieldMap)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["field_map"] = asdict(self.field_map)
        return payload

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "AppSettings":
        data = data or {}
        return cls(
            api_key=str(data.get("api_key", "")),
            base_url=str(data.get("base_url", cls.base_url)).rstrip("/"),
            model=str(data.get("model", cls.model)),
            default_deck=str(data.get("default_deck", cls.default_deck)),
            note_model_name=str(data.get("note_model_name", cls.note_model_name)),
            template_preset=str(data.get("template_preset", cls.template_preset)),
            skip_duplicates=bool(data.get("skip_duplicates", cls.skip_duplicates)),
            tags=str(data.get("tags", cls.tags)),
            timeout_seconds=float(data.get("timeout_seconds", cls.timeout_seconds)),
            retry_count=int(data.get("retry_count", cls.retry_count)),
            retry_delay_seconds=float(data.get("retry_delay_seconds", cls.retry_delay_seconds)),
            field_map=FieldMap.from_dict(data.get("field_map")),
        )


def load_settings() -> AppSettings:
    env_values = load_env_file()
    state_values = load_json_file(STATE_PATH)

    merged: Dict[str, Any] = {}
    merged.update(state_values)
    merged["api_key"] = os.environ.get("SILICONFLOW_API_KEY", env_values.get("SILICONFLOW_API_KEY", merged.get("api_key", "")))
    merged["base_url"] = os.environ.get("SILICONFLOW_BASE_URL", env_values.get("SILICONFLOW_BASE_URL", merged.get("base_url", AppSettings.base_url))).rstrip("/")
    merged["model"] = os.environ.get("LLM_MODEL", env_values.get("LLM_MODEL", merged.get("model", AppSettings.model)))
    merged["default_deck"] = os.environ.get("DEFAULT_DECK", env_values.get("DEFAULT_DECK", merged.get("default_deck", AppSettings.default_deck)))
    merged["note_model_name"] = os.environ.get("NOTE_MODEL_NAME", env_values.get("NOTE_MODEL_NAME", merged.get("note_model_name", AppSettings.note_model_name)))
    merged["template_preset"] = os.environ.get("TEMPLATE_PRESET", env_values.get("TEMPLATE_PRESET", merged.get("template_preset", AppSettings.template_preset)))
    merged["skip_duplicates"] = _parse_bool(
        os.environ.get("SKIP_DUPLICATES", env_values.get("SKIP_DUPLICATES")),
        bool(merged.get("skip_duplicates", AppSettings.skip_duplicates)),
    )
    merged["tags"] = os.environ.get("DEFAULT_TAGS", env_values.get("DEFAULT_TAGS", merged.get("tags", AppSettings.tags)))
    merged["timeout_seconds"] = _parse_float(
        os.environ.get("TIMEOUT_SECONDS", env_values.get("TIMEOUT_SECONDS")),
        float(merged.get("timeout_seconds", AppSettings.timeout_seconds)),
    )
    merged["retry_count"] = _parse_int(
        os.environ.get("RETRY_COUNT", env_values.get("RETRY_COUNT")),
        int(merged.get("retry_count", AppSettings.retry_count)),
    )
    merged["retry_delay_seconds"] = _parse_float(
        os.environ.get("RETRY_DELAY_SECONDS", env_values.get("RETRY_DELAY_SECONDS")),
        float(merged.get("retry_delay_seconds", AppSettings.retry_delay_seconds)),
    )

    field_map_values = {}
    for key in FieldMap().__dict__.keys():
        env_key = f"ANKI_FIELD_{key.upper()}"
        field_map_values[key] = os.environ.get(
            env_key,
            env_values.get(
                env_key,
                merged.get("field_map", {}).get(key) if isinstance(merged.get("field_map"), dict) else getattr(FieldMap(), key),
            ),
        )
    merged["field_map"] = field_map_values

    return AppSettings.from_dict(merged)
