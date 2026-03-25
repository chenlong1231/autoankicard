from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import json
import ctypes
import queue
import threading
import tkinter.font as tkfont
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from anki_client import AnkiConnectClient
from config import HISTORY_PATH, LOG_PATH, STATE_PATH, AppSettings, load_json_file, load_settings, save_json_file
from llm_client import SiliconFlowClient
from renderers import (
    PRESETS,
    render_back_html,
    render_front_html,
    render_front_preview_text,
)


def _enable_windows_dpi_awareness() -> None:
    if not hasattr(ctypes, "windll"):
        return

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


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
        self._dpi_scale = 1.0
        self._font_zoom_factor = 1.0
        self._dpi_sync_job: Optional[str] = None

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
        self.root.bind("<Configure>", self._schedule_dpi_sync, add="+")
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
        self.generate_tab.columnconfigure(1, weight=4)
        self.generate_tab.rowconfigure(0, weight=1)

        left = ttk.Frame(self.generate_tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(1, weight=1)

        zoom_row = ttk.Frame(left)
        zoom_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        zoom_row.columnconfigure(2, weight=1)
        ttk.Button(zoom_row, text="-10%", command=lambda: self.adjust_font_zoom(-0.1)).grid(row=0, column=0, sticky="w")
        ttk.Button(zoom_row, text="+10%", command=lambda: self.adjust_font_zoom(0.1)).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(zoom_row, text="Reset", command=self.reset_font_zoom).grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.font_zoom_label_var = tk.StringVar(value="Font: 100%")
        ttk.Label(zoom_row, textvariable=self.font_zoom_label_var).grid(row=0, column=3, sticky="e")

        ttk.Label(left, text="Word", font=("Segoe UI", 12, "bold")).grid(row=1, column=0, columnspan=3, sticky="w")
        self.word_var = tk.StringVar(value="example")
        self.word_entry = ttk.Entry(left, textvariable=self.word_var)
        self.word_entry.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 10))

        ttk.Label(left, text="Deck").grid(row=3, column=0, sticky="w")
        self.deck_var = tk.StringVar()
        self.deck_combo = ttk.Combobox(left, textvariable=self.deck_var, values=[self.settings.default_deck], state="readonly")
        self.deck_combo.grid(row=3, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(left, text="Refresh", command=self._refresh_anki_lists).grid(row=3, column=2, sticky="ew")

        ttk.Label(left, text="Model").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(left, textvariable=self.model_var, values=[self.settings.note_model_name], state="readonly")
        self.model_combo.grid(row=4, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Button(left, text="Refresh", command=self._refresh_anki_lists).grid(row=4, column=2, sticky="ew", pady=(8, 0))

        ttk.Label(left, text="Template preset").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.preset_var = tk.StringVar(value=self.settings.template_preset)
        self.preset_combo = ttk.Combobox(left, textvariable=self.preset_var, values=list(PRESETS.keys()), state="readonly")
        self.preset_combo.grid(row=5, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Label(left, text="HTML preset").grid(row=5, column=2, sticky="w", pady=(8, 0))

        ttk.Label(left, text="Tags").grid(row=6, column=0, sticky="w", pady=(8, 0))
        self.tags_var = tk.StringVar(value=self.settings.tags)
        ttk.Entry(left, textvariable=self.tags_var).grid(row=6, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Label(left, text="Comma or space separated").grid(row=6, column=2, sticky="w", pady=(8, 0))

        self.skip_duplicates_var = tk.BooleanVar(value=self.settings.skip_duplicates)
        ttk.Checkbutton(left, text="Skip duplicates", variable=self.skip_duplicates_var).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

        button_row = ttk.Frame(left)
        button_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        button_row.columnconfigure(2, weight=1)
        self.translate_button = ttk.Button(button_row, text="Translate", command=self.start_translation)
        self.translate_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.push_button = ttk.Button(button_row, text="Push to Anki", command=self.push_pending_to_anki, state="disabled")
        self.push_button.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(button_row, text="Save Settings", command=self.save_settings_from_ui).grid(row=0, column=2, sticky="ew")

        right = ttk.Frame(self.generate_tab)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=5)
        right.rowconfigure(1, weight=3)
        right.rowconfigure(2, weight=1)

        self.back_frame = ttk.LabelFrame(right, text="Back Preview", padding=10)
        self.back_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.back_frame.columnconfigure(0, weight=1)
        self.back_frame.rowconfigure(0, weight=1)

        self.front_frame = ttk.LabelFrame(right, text="Front Preview", padding=10)
        self.front_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        self.front_frame.columnconfigure(0, weight=1)
        self.front_frame.rowconfigure(0, weight=1)

        self.status_frame = ttk.LabelFrame(right, text="Status", padding=10)
        self.status_frame.grid(row=2, column=0, sticky="nsew")
        self.status_frame.columnconfigure(0, weight=1)
        self.status_frame.rowconfigure(0, weight=1)

        self.back_preview_text = tk.Text(self.back_frame, wrap="word", height=22, font=("Segoe UI", 16))
        self.back_preview_text.grid(row=0, column=0, sticky="nsew")
        self.front_preview_text = tk.Text(self.front_frame, wrap="word", height=9, font=("Segoe UI", 11))
        self.front_preview_text.grid(row=0, column=0, sticky="nsew")
        self.status_preview_text = tk.Text(self.status_frame, wrap="word", height=8, font=("Segoe UI", 10))
        self.status_preview_text.grid(row=0, column=0, sticky="nsew")

        self._configure_preview_styles()

        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(left, textvariable=self.status_var)
        self.status_label.grid(row=9, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.root.after(100, self._sync_window_dpi)
        self._apply_font_zoom()

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
            ("Max tokens", "max_tokens", str(self.settings.max_tokens)),
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

        self.enable_thinking_var = tk.BooleanVar(value=self.settings.enable_thinking)
        thinking_row = len(entries)
        ttk.Label(self.settings_inner, text="Enable thinking").grid(row=thinking_row, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Checkbutton(self.settings_inner, variable=self.enable_thinking_var).grid(row=thinking_row, column=1, sticky="w", pady=4)

        self.settings_inner.columnconfigure(1, weight=1)
        ttk.Button(self.settings_inner, text="Apply Settings", command=self.save_settings_from_ui).grid(
            row=len(entries) + 1, column=0, columnspan=2, sticky="ew", pady=(12, 0)
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
        self.settings_vars["max_tokens"].set(str(self.settings.max_tokens))
        self.settings_vars["default_deck"].set(self.settings.default_deck)
        self.settings_vars["note_model_name"].set(self.settings.note_model_name)
        self.settings_vars["template_preset"].set(self.settings.template_preset)
        self.settings_vars["tags"].set(self.settings.tags)
        self.settings_vars["timeout_seconds"].set(str(self.settings.timeout_seconds))
        self.settings_vars["retry_count"].set(str(self.settings.retry_count))
        self.settings_vars["retry_delay_seconds"].set(str(self.settings.retry_delay_seconds))
        self.enable_thinking_var.set(self.settings.enable_thinking)
        for key in self.settings.field_map.__dict__.keys():
            self.settings_vars[key].set(getattr(self.settings.field_map, key))
        self.deck_var.set(self.settings.default_deck)
        self.model_var.set(self.settings.note_model_name)

    def _sync_active_targets_to_settings(self) -> None:
        if self.deck_var.get().strip():
            self.settings_vars["default_deck"].set(self.deck_var.get().strip())
        if self.model_var.get().strip():
            self.settings_vars["note_model_name"].set(self.model_var.get().strip())

    def _sync_settings_to_active_targets(self) -> None:
        deck = self.settings.default_deck.strip()
        model = self.settings.note_model_name.strip()
        if deck:
            self.deck_var.set(deck)
        if model:
            self.model_var.set(model)

    def _collect_settings_from_ui(self) -> AppSettings:
        field_map_data = {key: self.settings_vars[key].get().strip() for key in self.settings.field_map.__dict__.keys()}
        field_map = self.settings.field_map.from_dict(field_map_data)
        return AppSettings(
            api_key=self.settings_vars["api_key"].get().strip(),
            base_url=self.settings_vars["base_url"].get().strip().rstrip("/"),
            model=self.settings_vars["model"].get().strip(),
            max_tokens=int(float(self.settings_vars["max_tokens"].get().strip() or self.settings.max_tokens)),
            enable_thinking=self.enable_thinking_var.get(),
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
        self._sync_settings_to_active_targets()
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
        word = self.word_var.get().strip()
        if not word:
            messagebox.showwarning("Missing input", "Enter one word.")
            return
        if not self.save_settings_from_ui(refresh=False):
            return
        self._sync_active_targets_to_settings()
        self.translate_button.config(state="disabled")
        self.push_button.config(state="disabled")
        self.pending_record = None
        self.status_var.set("Translating 1 card...")
        self.logger.info("Starting translation for word %s", word)

        def worker() -> None:
            try:
                record = self._translate_word(word, 1, 1, self.settings)
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

        note_id = self.anki_client.add_note(
            deck_name,
            model_name,
            fields,
            tags=[],
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
                        self.settings_vars["default_deck"].set(self.deck_var.get())
                    if models:
                        self.model_combo["values"] = models
                        if self.model_var.get() not in models:
                            self.model_var.set(self.settings.note_model_name if self.settings.note_model_name in models else models[0])
                        self.settings_vars["note_model_name"].set(self.model_var.get())
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
        self._set_text(self.status_preview_text, "\n".join(summary))
        card = record.card or {}
        self._set_text(self.front_preview_text, render_front_preview_text(card))
        self._set_back_preview(card)
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
        self._set_text(self.status_preview_text, "")
        self._set_text(self.front_preview_text, "")
        self._set_text(self.back_preview_text, "")
        self.status_var.set("History cleared")
        self.logger.info("Local history cleared")

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="normal")

    def _configure_preview_styles(self) -> None:
        self.back_preview_text.tag_configure(
            "header",
            font=("Segoe UI", 18, "bold"),
            foreground="#1f4e79",
            spacing3=8,
        )
        self.back_preview_text.tag_configure(
            "section",
            font=("Segoe UI", 14, "bold"),
            foreground="#2b4a66",
            spacing1=6,
            spacing3=4,
        )
        self.back_preview_text.tag_configure(
            "label",
            font=("Segoe UI", 12, "bold"),
            foreground="#17324a",
        )
        self.back_preview_text.tag_configure(
            "accent",
            font=("Segoe UI", 12, "bold"),
            foreground="#7a4f1f",
        )
        self.back_preview_text.tag_configure(
            "body",
            font=("Segoe UI", 12),
            foreground="#22313f",
        )
        self.back_preview_text.configure(spacing1=4, spacing2=2, spacing3=8, padx=4, pady=4)
        self.back_preview_text.config(state="normal")

    def _insert_back_line(self, text: str, *tags: str) -> None:
        self.back_preview_text.insert("end", text, tags)

    def _set_back_preview(self, card: Dict[str, object]) -> None:
        self.back_preview_text.configure(state="normal")
        self.back_preview_text.delete("1.0", "end")

        self._insert_back_line("📌 ", "header")
        self._insert_back_line("Meaning (English-English)\n", "header")

        meanings = card.get("meanings", [])
        for index, meaning in enumerate(meanings if isinstance(meanings, list) else []):
            if not isinstance(meaning, dict):
                continue
            pos = str(meaning.get("part_of_speech", "")).strip()
            definition = str(meaning.get("definition", "")).strip()
            example_sentence = str(meaning.get("example_sentence", "")).strip()
            example_meaning = str(meaning.get("meaning", "")).strip()
            self._insert_back_line(f"{index + 1}. ", "section")
            if pos:
                self._insert_back_line(f"{pos} ", "label")
            self._insert_back_line(f"{definition}\n", "body")
            if example_sentence:
                self._insert_back_line("   e.g. ", "accent")
                self._insert_back_line(f"{example_sentence}\n", "body")
            if example_meaning:
                self._insert_back_line("   Meaning: ", "accent")
                self._insert_back_line(f"{example_meaning}\n", "body")
            self._insert_back_line("\n")

        self._insert_back_line("📌 Common collocations\n", "section")
        collocations = card.get("collocations", [])
        for collocation in collocations if isinstance(collocations, list) else []:
            if not isinstance(collocation, dict):
                continue
            phrase = str(collocation.get("phrase", "")).strip()
            gloss = str(collocation.get("gloss", "")).strip()
            if not phrase:
                continue
            self._insert_back_line(f"• {phrase}", "label")
            if gloss:
                self._insert_back_line(f"  {gloss}\n", "body")
            else:
                self._insert_back_line("\n", "body")

        self._insert_back_line("\n📌 Extra examples\n", "section")
        examples = card.get("extra_examples", [])
        for example in examples if isinstance(examples, list) else []:
            if not isinstance(example, dict):
                continue
            sentence = str(example.get("sentence", "")).strip()
            meaning = str(example.get("meaning", "")).strip()
            if not sentence:
                continue
            self._insert_back_line(f"• {sentence}\n", "body")
            if meaning:
                self._insert_back_line("   Meaning: ", "accent")
                self._insert_back_line(f"{meaning}\n", "body")
            self._insert_back_line("\n")

        self.back_preview_text.configure(state="disabled")

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

    def _get_window_dpi(self) -> Optional[int]:
        if not hasattr(ctypes, "windll"):
            return None
        try:
            hwnd = self.root.winfo_id()
            get_dpi_for_window = getattr(ctypes.windll.user32, "GetDpiForWindow", None)
            if get_dpi_for_window is None:
                return None
            return int(get_dpi_for_window(hwnd))
        except Exception:
            return None

    def _sync_window_dpi(self) -> None:
        dpi = self._get_window_dpi()
        if not dpi:
            return
        scale = dpi / 96.0
        if abs(scale - self._dpi_scale) < 0.02:
            return
        self._dpi_scale = scale
        self._apply_font_zoom()
        self.logger.info("Adjusted UI scale to %.2f for DPI %s", scale, dpi)

    def _schedule_dpi_sync(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        if self._dpi_sync_job is not None:
            try:
                self.root.after_cancel(self._dpi_sync_job)
            except tk.TclError:
                pass
        self._dpi_sync_job = self.root.after(150, self._run_scheduled_dpi_sync)

    def _run_scheduled_dpi_sync(self) -> None:
        self._dpi_sync_job = None
        self._sync_window_dpi()

    def _apply_font_zoom(self) -> None:
        scale = max(0.75, min(1.6, self._dpi_scale * self._font_zoom_factor))

        def resize_named_font(name: str, base_size: int, weight: str = "normal") -> None:
            try:
                font = tkfont.nametofont(name)
                font.configure(size=max(1, int(round(base_size * scale))), weight=weight)
            except tk.TclError:
                pass

        resize_named_font("TkDefaultFont", 10)
        resize_named_font("TkTextFont", 10)
        resize_named_font("TkMenuFont", 10)
        resize_named_font("TkHeadingFont", 10, "bold")
        resize_named_font("TkFixedFont", 10)
        self.back_preview_text.configure(font=("Segoe UI", max(1, int(round(16 * scale)))))
        self.front_preview_text.configure(font=("Segoe UI", max(1, int(round(11 * scale)))))
        self.status_preview_text.configure(font=("Segoe UI", max(1, int(round(10 * scale)))))
        self.font_zoom_label_var.set(f"Font: {int(round(self._font_zoom_factor * 100))}%")

    def adjust_font_zoom(self, delta: float) -> None:
        self._font_zoom_factor = max(0.5, min(2.0, self._font_zoom_factor + delta))
        self._apply_font_zoom()

    def reset_font_zoom(self) -> None:
        self._font_zoom_factor = 1.0
        self._apply_font_zoom()


def main() -> None:
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except tk.TclError:
        pass
    AutoAnkiCardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
