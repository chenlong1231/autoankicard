from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import AppSettings


class AnkiConnectError(RuntimeError):
    pass


@dataclass
class AnkiNoteResult:
    note_id: Optional[int]
    duplicate: bool
    message: str


class AnkiConnectClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.endpoint = "http://localhost:8765"

    def _call(self, action: str, params: Optional[Dict] = None) -> Dict:
        payload = {"action": action, "version": 6, "params": params or {}}
        body = json.dumps(payload).encode("utf-8")
        request = Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                data = response.read().decode("utf-8")
        except HTTPError as exc:
            raise AnkiConnectError(f"AnkiConnect HTTP {exc.code}") from exc
        except URLError as exc:
            raise AnkiConnectError("Could not reach AnkiConnect at http://localhost:8765") from exc

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise AnkiConnectError(f"AnkiConnect returned invalid JSON: {exc}") from exc
        if parsed.get("error"):
            raise AnkiConnectError(str(parsed["error"]))
        return parsed

    def deck_names(self) -> List[str]:
        return list(self._call("deckNames").get("result", []))

    def create_deck(self, deck_name: str) -> None:
        self._call("createDeck", {"deck": deck_name})

    def model_names(self) -> List[str]:
        return list(self._call("modelNames").get("result", []))

    def find_notes(self, query: str) -> List[int]:
        return list(self._call("findNotes", {"query": query}).get("result", []))

    def notes_info(self, note_ids: List[int]) -> List[Dict]:
        if not note_ids:
            return []
        return list(self._call("notesInfo", {"notes": note_ids}).get("result", []))

    def find_duplicate_note_ids(self, deck_name: str, model_name: str, word_field_name: str, word: str) -> List[int]:
        query = f'deck:"{deck_name}" note:"{model_name}"'
        note_ids = self.find_notes(query)
        if not note_ids:
            return []
        matches: List[int] = []
        word_normalized = word.strip().lower()
        for note in self.notes_info(note_ids):
            fields = note.get("fields", {})
            field = fields.get(word_field_name, {})
            value = str(field.get("value", "")).strip().lower()
            if value == word_normalized:
                matches.append(int(note["noteId"]))
        return matches

    def add_note(
        self,
        deck_name: str,
        model_name: str,
        fields: Dict[str, str],
        tags: Optional[List[str]] = None,
    ) -> int:
        payload = {
            "note": {
                "deckName": deck_name,
                "modelName": model_name,
                "fields": fields,
                "tags": tags or [],
            }
        }
        result = self._call("addNote", payload).get("result")
        if result is None:
            raise AnkiConnectError("AnkiConnect did not return a note id")
        return int(result)
