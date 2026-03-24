from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import json
import queue
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from anki_client import AnkiConnectClient
from config import HISTORY_PATH, LOG_PATH, STATE_PATH, AppSettings, load_json_file, load_settings, save_json_file
from llm_client import SiliconFlowClient
from renderers import PRESETS, render_back_html, render_front_html


@dataclass
class CardRunRecord:
    timestamp: str
    word: str
    status: str
    note_id: Optional[int]
    deck_name: str
    model_name: str
    preset: str
    error: str = ""
    front_html: str = ""
    back_html: str = ""
    raw_json: str = ""
    card: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class QueueLogHandler(logging.Handler):
    def __init__(self, target_queue: "queue.Queue[Dict]") -> None:
        super().__init__()
        self.target_queue = target_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self.target_queue.put(
            {
                "kind": "log",
                "level": record.levelname,
                "message": message,
            }
        )


class AutoAnkiCardApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("autoankicard")
        self.root.geometry("1320x900")

        self.settings = load_settings()
        self.history: List[CardRunRecord] = self._load_history()
        self.worker_queue: "queue.Queue[Dict]" = queue.Queue()
        self.latest_record: Optional[CardRunRecord] = None
        self.pending_record: Optional[CardRunRecord] = None
        self.logger = logging.getLogger("autoankicard")
        self.logger.setLevel(logging.INFO)
        self._configure_logging()

        self.anki_client = AnkiConnectClient(self.settings)
        self.llm_client = SiliconFlowClient(self.settings)

        self._build_ui()
        self._refresh_settings_fields()
        self._refresh_history_tree()
        self._refresh_anki_lists()
        self._sync_active_targets_to_settings()
        self.logger.info("Application started")
        self._poll_queue()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=0, column=0, sticky="nsew")

        self.generate_tab = ttk.Frame(notebook, padding=12)
        self.settings_tab = ttk.Frame(notebook, padding=12)
        self.history_tab = ttk.Frame(notebook, padding=12)
        self.log_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.generate_tab, text="Generate")
        notebook.add(self.settings_tab, text="Settings")
        notebook.add(self.history_tab, text="History")
        notebook.add(self.log_tab, text="Logs")

        self._build_generate_tab()
        self._build_settings_tab()
        self._build_history_tab()
        self._build_log_tab()

    def _build_generate_tab(self) -> None:
        self.generate_tab.columnconfigure(0, weight=1)
        self.generate_tab.columnconfigure(1, weight=2)
        self.generate_tab.rowconfigure(0, weight=1)

        left = ttk.Frame(self.generate_tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(1, weight=1)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Words", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        self.words_text = tk.Text(left, height=12, wrap="word")
        self.words_text.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(6, 10))
        self.words_text.insert("1.0", "example")

        ttk.Label(left, text="Deck").grid(row=2, column=0, sticky="w")
        self.deck_var = tk.StringVar()
        self.deck_combo = ttk.Combobox(left, textvariable=self.deck_var, values=[self.settings.default_deck], state="readonly")
        self.deck_combo.grid(row=2, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(left, text="Refresh", command=self._refresh_anki_lists).grid(row=2, column=2, sticky="ew")

        ttk.Label(left, text="Model").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(left, textvariable=self.model_var, values=[self.settings.note_model_name], state="readonly")
        self.model_combo.grid(row=3, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Button(left, text="Refresh", command=self._refresh_anki_lists).grid(row=3, column=2, sticky="ew", pady=(8, 0))

        ttk.Label(left, text="Template preset").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.preset_var = tk.StringVar(value=self.settings.template_preset)
        self.preset_combo = ttk.Combobox(left, textvariable=self.preset_var, values=list(PRESETS.keys()), state="readonly")
        self.preset_combo.grid(row=4, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Label(left, text="HTML preset").grid(row=4, column=2, sticky="w", pady=(8, 0))

        ttk.Label(left, text="Tags").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.tags_var = tk.StringVar(value=self.settings.tags)
        ttk.Entry(left, textvariable=self.tags_var).grid(row=5, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Label(left, text="Comma or space separated").grid(row=5, column=2, sticky="w", pady=(8, 0))

        self.skip_duplicates_var = tk.BooleanVar(value=self.settings.skip_duplicates)
        ttk.Checkbutton(left, text="Skip duplicates", variable=self.skip_duplicates_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

        button_row = ttk.Frame(left)
        button_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        button_row.columnconfigure(2, weight=1)
        self.translate_button = ttk.Button(button_row, text="Translate", command=self.start_translation)
        self.translate_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.push_button = ttk.Button(button_row, text="Push to Anki", command=self.push_pending_to_anki, state="disabled")
        self.push_button.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(button_row, text="Save Settings", command=self.save_settings_from_ui).grid(row=0, column=2, sticky="ew")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(left, textvariable=self.status_var).grid(row=8, column=0, columnspan=3, sticky="w", pady=(12, 0))

        right = ttk.Frame(self.generate_tab)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        preview_tabs = ttk.Notebook(right)
        preview_tabs.grid(row=0, column=0, sticky="nsew")

        self.summary_text = tk.Text(preview_tabs, wrap="word")
        self.front_text = tk.Text(preview_tabs, wrap="word")
        self.back_text = tk.Text(preview_tabs, wrap="word")
        self.raw_text = tk.Text(preview_tabs, wrap="word")
        preview_tabs.add(self.summary_text, text="Summary")
        preview_tabs.add(self.front_text, text="Front HTML")
        preview_tabs.add(self.back_text, text="Back HTML")
        preview_tabs.add(self.raw_text, text="Raw JSON")

    def _build_settings_tab(self) -> None:
        canvas = tk.Canvas(self.settings_tab, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.settings_tab, orient="vertical", command=canvas.yview)
        self.settings_inner = ttk.Frame(canvas)
        self.settings_inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.settings_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.settings_vars: Dict[str, tk.StringVar] = {}
        entries = [
            ("API key", "api_key", self.settings.api_key),
            ("Base URL", "base_url", self.settings.base_url),
            ("LLM model", "model", self.settings.model),
            ("Default deck", "default_deck", self.settings.default_deck),
            ("Note model", "note_model_name", self.settings.note_model_name),
            ("Template preset", "template_preset", self.settings.template_preset),
            ("Tags", "tags", self.settings.tags),
            ("Timeout seconds", "timeout_seconds", str(self.settings.timeout_seconds)),
            ("Retry count", "retry_count", str(self.settings.retry_count)),
            ("Retry delay seconds", "retry_delay_seconds", str(self.settings.retry_delay_seconds)),
            ("Front field", "front", self.settings.field_map.front),
            ("Back field", "back", self.settings.field_map.back),
            ("Word field", "word", self.settings.field_map.word),
            ("Phonetic field", "phonetic", self.settings.field_map.phonetic),
            ("Part of speech field", "part_of_speech", self.settings.field_map.part_of_speech),
            ("Definition field", "definition", self.settings.field_map.definition),
            ("Translation field", "translation", self.settings.field_map.translation),
            ("Example sentence field", "example_sentence", self.settings.field_map.example_sentence),
            ("Example translation field", "example_translation", self.settings.field_map.example_translation),
            ("Synonyms field", "synonyms", self.settings.field_map.synonyms),
            ("Antonyms field", "antonyms", self.settings.field_map.antonyms),
            ("Collocations field", "collocations", self.settings.field_map.collocations),
            ("Memory tip field", "memory_tip", self.settings.field_map.memory_tip),
        ]

        for row, (label, attr, value) in enumerate(entries):
            ttk.Label(self.settings_inner, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            var = tk.StringVar(value=value)
            ttk.Entry(self.settings_inner, textvariable=var, width=48, show="*" if attr == "api_key" else "").grid(
                row=row, column=1, sticky="ew", pady=4
            )
            self.settings_vars[attr] = var

        self.settings_inner.columnconfigure(1, weight=1)
        ttk.Button(self.settings_inner, text="Apply Settings", command=self.save_settings_from_ui).grid(
            row=len(entries), column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_history_tab(self) -> None:
        self.history_tab.columnconfigure(0, weight=1)
        self.history_tab.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.history_tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(toolbar, text="Refresh", command=self._refresh_history_tree).pack(side="left")
        ttk.Button(toolbar, text="Clear local history", command=self.clear_history).pack(side="left", padx=(8, 0))

        self.history_tree = ttk.Treeview(
            self.history_tab,
            columns=("time", "word", "status", "note_id", "deck", "model", "preset"),
            show="headings",
        )
        for column, width in [
            ("time", 160),
            ("word", 120),
            ("status", 100),
            ("note_id", 90),
            ("deck", 160),
            ("model", 180),
            ("preset", 120),
        ]:
            self.history_tree.heading(column, text=column.title())
            self.history_tree.column(column, width=width, anchor="w")
        self.history_tree.grid(row=1, column=0, sticky="nsew")
        self.history_tree.bind("<<TreeviewSelect>>", self._on_history_select)

    def _build_log_tab(self) -> None:
        self.log_tab.columnconfigure(0, weight=1)
        self.log_tab.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.log_tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(toolbar, text="Refresh", command=self._reload_log_tail).pack(side="left")
        ttk.Button(toolbar, text="Open Log File", command=self.open_log_file).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Clear View", command=self.clear_log_view).pack(side="left", padx=(8, 0))

        self.log_text = tk.Text(self.log_tab, wrap="none")
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_scroll = ttk.Scrollbar(self.log_tab, orient="vertical", command=self.log_text.yview)
        self.log_scroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        self._reload_log_tail()

    def _refresh_settings_fields(self) -> None:
        self.settings_vars["api_key"].set(self.settings.api_key)
        self.settings_vars["base_url"].set(self.settings.base_url)
        self.settings_vars["model"].set(self.settings.model)
        self.settings_vars["default_deck"].set(self.settings.default_deck)
        self.settings_vars["note_model_name"].set(self.settings.note_model_name)
        self.settings_vars["template_preset"].set(self.settings.template_preset)
        self.settings_vars["tags"].set(self.settings.tags)
        self.settings_vars["timeout_seconds"].set(str(self.settings.timeout_seconds))
        self.settings_vars["retry_count"].set(str(self.settings.retry_count))
        self.settings_vars["retry_delay_seconds"].set(str(self.settings.retry_delay_seconds))
        for key in self.settings.field_map.__dict__.keys():
            self.settings_vars[key].set(getattr(self.settings.field_map, key))
        self.deck_var.set(self.settings.default_deck)
        self.model_var.set(self.settings.note_model_name)

    def _sync_active_targets_to_settings(self) -> None:
        if self.deck_var.get().strip():
            self.settings_vars["default_deck"].set(self.deck_var.get().strip())
        if self.model_var.get().strip():
            self.settings_vars["note_model_name"].set(self.model_var.get().strip())

    def _collect_settings_from_ui(self) -> AppSettings:
        field_map_data = {key: self.settings_vars[key].get().strip() for key in self.settings.field_map.__dict__.keys()}
        field_map = self.settings.field_map.from_dict(field_map_data)
        return AppSettings(
            api_key=self.settings_vars["api_key"].get().strip(),
            base_url=self.settings_vars["base_url"].get().strip().rstrip("/"),
            model=self.settings_vars["model"].get().strip(),
            default_deck=self.settings_vars["default_deck"].get().strip(),
            note_model_name=self.settings_vars["note_model_name"].get().strip(),
            template_preset=self.settings_vars["template_preset"].get().strip() or "classic",
            tags=self.settings_vars["tags"].get().strip(),
            skip_duplicates=self.skip_duplicates_var.get(),
            timeout_seconds=float(self.settings_vars["timeout_seconds"].get().strip() or self.settings.timeout_seconds),
            retry_count=int(float(self.settings_vars["retry_count"].get().strip() or self.settings.retry_count)),
            retry_delay_seconds=float(self.settings_vars["retry_delay_seconds"].get().strip() or self.settings.retry_delay_seconds),
            field_map=field_map,
        )

    def save_settings_from_ui(self, refresh: bool = True) -> bool:
        try:
            self.settings = self._collect_settings_from_ui()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return False

        save_json_file(STATE_PATH, self.settings.to_dict())
        self.anki_client = AnkiConnectClient(self.settings)
        self.llm_client = SiliconFlowClient(self.settings)
        self.status_var.set("Settings saved")
        self.logger.info("Settings saved")
        self._refresh_anki_lists()
        if refresh:
            self._refresh_history_tree()
        return True

    def _refresh_anki_lists(self) -> None:
        def worker() -> None:
            try:
                decks = self.anki_client.deck_names()
                models = self.anki_client.model_names()
                self.worker_queue.put({"kind": "anki_lists", "decks": decks, "models": models})
                self.logger.info("Loaded %d deck(s) and %d model(s) from AnkiConnect", len(decks), len(models))
            except Exception as exc:
                self.logger.exception("Failed to refresh Anki lists")
                self.worker_queue.put({"kind": "error", "message": str(exc)})

        threading.Thread(target=worker, daemon=True).start()
        self.status_var.set("Refreshing Anki lists...")

    def start_translation(self) -> None:
        words = [line.strip() for line in self.words_text.get("1.0", "end").splitlines() if line.strip()]
        if not words:
            messagebox.showwarning("Missing input", "Enter at least one word.")
            return
        if not self.save_settings_from_ui(refresh=False):
            return
        self._sync_active_targets_to_settings()
        self.translate_button.config(state="disabled")
        self.push_button.config(state="disabled")
        self.pending_record = None
        self.status_var.set(f"Translating {len(words)} card(s)...")
        self.logger.info("Starting translation for %d word(s)", len(words))

        def worker() -> None:
            total = len(words)
            for index, word in enumerate(words, start=1):
                try:
                    record = self._translate_word(word, index, total, self.settings)
                except Exception as exc:
                    self.logger.exception("Generation failed for word %s", word)
                    record = CardRunRecord(
                        timestamp=self._timestamp(),
                        word=word,
                        status="error",
                        note_id=None,
                        deck_name=self.settings.default_deck,
                        model_name=self.settings.note_model_name,
                        preset=self.preset_var.get(),
                        error=str(exc),
                    )
                self.worker_queue.put({"kind": "record", "record": record})
            self.worker_queue.put({"kind": "done"})

        threading.Thread(target=worker, daemon=True).start()

    def _translate_word(self, word: str, index: int, total: int, settings: AppSettings) -> CardRunRecord:
        self.worker_queue.put({"kind": "status", "message": f"{index}/{total}: translating {word}"})
        self.logger.info("Translating word %s (%d/%d)", word, index, total)
        result = self.llm_client.generate_card_with_retry(word)
        front_html = render_front_html(result.card, preset_name=self.preset_var.get())
        back_html = render_back_html(result.card, preset_name=self.preset_var.get())
        deck_name = self._selected_deck_name()
        model_name = self._selected_model_name()
        return CardRunRecord(
            timestamp=self._timestamp(),
            word=result.card.word,
            status="translated",
            note_id=None,
            deck_name=deck_name,
            model_name=model_name,
            preset=self.preset_var.get(),
            front_html=front_html,
            back_html=back_html,
            raw_json=result.raw_text,
            card=result.card.to_dict(),
        )

    def push_pending_to_anki(self) -> None:
        if self.pending_record is None or self.pending_record.card is None:
            messagebox.showwarning("Nothing to push", "Translate a word first.")
            return
        if not self.save_settings_from_ui(refresh=False):
            return
        self._sync_active_targets_to_settings()

        self.push_button.config(state="disabled")
        self.translate_button.config(state="disabled")

        record = self.pending_record
        card = record.card
        settings = self.settings
        deck_name = self._selected_deck_name()
        model_name = self._selected_model_name()
        if not deck_name:
            messagebox.showerror("Missing deck", "Choose a deck before pushing to Anki.")
            self.translate_button.config(state="normal")
            self.push_button.config(state="normal" if self.pending_record is not None else "disabled")
            return
        if not model_name:
            messagebox.showerror("Missing model", "Choose a note model before pushing to Anki.")
            self.translate_button.config(state="normal")
            self.push_button.config(state="normal" if self.pending_record is not None else "disabled")
            return

        try:
            existing_decks = self.anki_client.deck_names()
            if deck_name not in existing_decks:
                self.logger.info("Deck %s was missing; creating it before push", deck_name)
                self.anki_client.create_deck(deck_name)
        except Exception as exc:
            self.logger.exception("Could not ensure deck %s exists", deck_name)
            self.translate_button.config(state="normal")
            self.push_button.config(state="normal" if self.pending_record is not None else "disabled")
            self.worker_queue.put({"kind": "error", "message": f"Could not prepare deck '{deck_name}': {exc}"})
            return

        fields = {
            "Front": record.front_html,
            "Back": record.back_html,
        }

        tags = self._build_tags(settings, str(card.get("part_of_speech", "")) or "unknown")
        note_id = self.anki_client.add_note(
            deck_name,
            model_name,
            fields,
            tags=tags,
        )
        status = "ok"
        error = ""
        self.logger.info("Added note %s for word %s", note_id, card.get("word", ""))

        pushed_record = CardRunRecord(
            timestamp=self._timestamp(),
            word=str(card.get("word", "")),
            status=status,
            note_id=note_id,
            deck_name=deck_name,
            model_name=model_name,
            preset=self.preset_var.get(),
            error=error,
            front_html=record.front_html,
            back_html=record.back_html,
            raw_json=record.raw_json,
            card=card,
        )
        self.worker_queue.put({"kind": "record", "record": pushed_record})
        self.worker_queue.put({"kind": "done"})
        self.status_var.set(f"Pushed '{card.get('word', '')}' to Anki")
        self.logger.info("Finished push flow for word %s", card.get("word", ""))

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self.worker_queue.get_nowait()
                kind = message.get("kind")
                if kind == "status":
                    self.status_var.set(message["message"])
                elif kind == "anki_lists":
                    decks = message.get("decks", [])
                    models = message.get("models", [])
                    if decks:
                        self.deck_combo["values"] = decks
                        if self.deck_var.get() not in decks:
                            self.deck_var.set(self.settings.default_deck if self.settings.default_deck in decks else decks[0])
                    if models:
                        self.model_combo["values"] = models
                        if self.model_var.get() not in models:
                            self.model_var.set(self.settings.note_model_name if self.settings.note_model_name in models else models[0])
                    self.status_var.set("Anki lists refreshed")
                elif kind == "record":
                    record = message["record"]
                    self.latest_record = record
                    self.history.append(record)
                    self._save_history()
                    self._refresh_history_tree()
                    self._show_record(record)
                elif kind == "done":
                    self.translate_button.config(state="normal")
                    if self.pending_record is not None and self.pending_record.status == "translated":
                        self.push_button.config(state="normal")
                        self.status_var.set("Translation complete. Ready to push.")
                    else:
                        self.push_button.config(state="disabled")
                        self.status_var.set("Generation complete")
                elif kind == "error":
                    self.logger.error("%s", message["message"])
                    self.status_var.set(message["message"])
                    messagebox.showerror("Error", message["message"])
                elif kind == "log":
                    self._append_log_line(message["level"], message["message"])
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _show_record(self, record: CardRunRecord) -> None:
        summary = [
            f"Time: {record.timestamp}",
            f"Word: {record.word}",
            f"Status: {record.status}",
            f"Note ID: {record.note_id}",
            f"Deck: {record.deck_name}",
            f"Model: {record.model_name}",
            f"Preset: {record.preset}",
        ]
        if record.error:
            summary.append(f"Error: {record.error}")
        self._set_text(self.summary_text, "\n".join(summary))
        self._set_text(self.front_text, record.front_html)
        self._set_text(self.back_text, record.back_html)
        raw_value = record.raw_json or json.dumps(record.card or {}, indent=2, ensure_ascii=False)
        self._set_text(self.raw_text, raw_value)
        if record.status == "translated":
            self.pending_record = record
            self.push_button.config(state="normal")
        elif record.status in {"ok", "skipped"}:
            self.pending_record = None
            self.push_button.config(state="disabled")

    def _refresh_history_tree(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for index, record in enumerate(reversed(self.history[-250:])):
            self.history_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    record.timestamp,
                    record.word,
                    record.status,
                    record.note_id or "",
                    record.deck_name,
                    record.model_name,
                    record.preset,
                ),
            )

    def _on_history_select(self, event: tk.Event) -> None:
        selection = self.history_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        record = list(reversed(self.history[-250:]))[index]
        self._show_record(record)

    def _load_history(self) -> List[CardRunRecord]:
        payload = load_json_file(HISTORY_PATH)
        records = []
        for item in payload.get("records", []):
            try:
                records.append(CardRunRecord(**item))
            except TypeError:
                continue
        return records

    def _save_history(self) -> None:
        payload = {"records": [record.to_dict() for record in self.history[-500:]]}
        save_json_file(HISTORY_PATH, payload)

    def clear_history(self) -> None:
        if not messagebox.askyesno("Clear history", "Delete the local history file?"):
            return
        self.history = []
        self._save_history()
        self._refresh_history_tree()
        self._set_text(self.summary_text, "")
        self._set_text(self.front_text, "")
        self._set_text(self.back_text, "")
        self._set_text(self.raw_text, "")
        self.status_var.set("History cleared")
        self.logger.info("Local history cleared")

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="normal")

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _build_tags(self, settings: AppSettings, part_of_speech: str) -> List[str]:
        tags = ["autoankicard", settings.template_preset, part_of_speech]
        tags.extend([tag for tag in settings.tags.replace(",", " ").split() if tag])
        deduped: List[str] = []
        seen = set()
        for tag in tags:
            cleaned = tag.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped

    def _selected_deck_name(self) -> str:
        deck = self.deck_var.get().strip()
        if deck:
            return deck
        return self.settings.default_deck.strip()

    def _selected_model_name(self) -> str:
        model = self.model_var.get().strip()
        if model:
            return model
        return self.settings.note_model_name.strip()

    def _configure_logging(self) -> None:
        self.logger.handlers.clear()
        self.logger.propagate = False

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        file_handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        ui_handler = QueueLogHandler(self.worker_queue)
        ui_handler.setFormatter(formatter)
        ui_handler.setLevel(logging.INFO)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(ui_handler)

    def _append_log_line(self, level: str, message: str) -> None:
        self.log_text.insert("end", f"[{level}] {message}\n")
        self.log_text.see("end")

    def _reload_log_tail(self, max_lines: int = 300) -> None:
        self.log_text.delete("1.0", "end")
        if not LOG_PATH.exists():
            self.log_text.insert("end", "Log file has not been created yet.\n")
            return
        try:
            lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            self.log_text.insert("end", f"Could not read log file: {exc}\n")
            return
        for line in lines[-max_lines:]:
            self.log_text.insert("end", line + "\n")
        self.log_text.see("end")

    def clear_log_view(self) -> None:
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "View cleared. Existing log file was not modified.\n")

    def open_log_file(self) -> None:
        try:
            import os
            os.startfile(str(LOG_PATH))
        except Exception as exc:
            messagebox.showerror("Open log file", str(exc))
            self.logger.exception("Failed to open log file")


def main() -> None:
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass
    AutoAnkiCardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
