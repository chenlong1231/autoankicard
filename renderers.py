from __future__ import annotations

from html import escape
from typing import Dict, Iterable

from schema import VocabularyCardData


PRESETS = {
    "classic": {
        "bg": "#f6f8fb",
        "panel": "#ffffff",
        "accent": "#1f4e79",
        "accent_soft": "#dce9f7",
        "text": "#16212d",
        "muted": "#5b6b7a",
        "font": '"Segoe UI", "Noto Sans", Arial, sans-serif',
    },
    "study": {
        "bg": "#f9f7f2",
        "panel": "#fffdf8",
        "accent": "#7a4f1f",
        "accent_soft": "#f5e7d8",
        "text": "#2b241f",
        "muted": "#7d6f62",
        "font": '"Georgia", "Noto Serif SC", serif',
    },
    "compact": {
        "bg": "#eef5f2",
        "panel": "#ffffff",
        "accent": "#1f6b57",
        "accent_soft": "#d7ece5",
        "text": "#17332d",
        "muted": "#54675f",
        "font": '"Aptos", "Segoe UI", Arial, sans-serif',
    },
}


def _preset(name: str) -> Dict[str, str]:
    return PRESETS.get(name, PRESETS["classic"])


def _list_items(items: Iterable[str]) -> str:
    values = [escape(item) for item in items if item]
    if not values:
        return "<span class=\"empty\">None</span>"
    return "<ul>" + "".join(f"<li>{value}</li>" for value in values) + "</ul>"


def _base_css(preset_name: str) -> str:
    preset = _preset(preset_name)
    return f"""
        body {{
            margin: 0;
            background: {preset["bg"]};
            color: {preset["text"]};
            font-family: {preset["font"]};
        }}
        .card {{
            box-sizing: border-box;
            padding: 22px 24px;
            min-height: 220px;
            border-radius: 18px;
            background: {preset["panel"]};
            border: 1px solid rgba(0, 0, 0, 0.08);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.06);
        }}
        .word {{
            font-size: 2rem;
            font-weight: 700;
            color: {preset["accent"]};
            line-height: 1.1;
        }}
        .subtle {{
            color: {preset["muted"]};
        }}
        .chip {{
            display: inline-block;
            margin-right: 6px;
            margin-bottom: 6px;
            padding: 4px 10px;
            border-radius: 999px;
            background: {preset["accent_soft"]};
            color: {preset["accent"]};
            font-size: 0.84rem;
        }}
        .section {{
            margin-top: 14px;
        }}
        .section h4 {{
            margin: 0 0 6px;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: {preset["accent"]};
        }}
        .definition {{
            line-height: 1.6;
        }}
        ul {{
            margin: 6px 0 0 20px;
            padding: 0;
        }}
        .empty {{
            color: {preset["muted"]};
            font-style: italic;
        }}
    """


def render_front_html(card: VocabularyCardData, preset_name: str = "classic") -> str:
    part = escape(card.part_of_speech) if card.part_of_speech else ""
    phonetic = escape(card.phonetic) if card.phonetic else ""
    definition = escape(card.definition)
    chips = []
    if part:
        chips.append(f'<span class="chip">{part}</span>')
    if phonetic:
        chips.append(f'<span class="chip">{phonetic}</span>')
    return f"""<div class="card">
<style>{_base_css(preset_name)}</style>
<div class="word">{escape(card.word)}</div>
<div class="section subtle">{''.join(chips)}</div>
<div class="section definition">{definition}</div>
</div>"""


def render_back_html(card: VocabularyCardData, preset_name: str = "classic") -> str:
    memory_tip = escape(card.memory_tip) if card.memory_tip else '<span class="empty">None</span>'
    return f"""<div class="card">
<style>{_base_css(preset_name)}</style>
<div class="word">{escape(card.word)}</div>
<div class="section">
  <h4>Translation</h4>
  <div class="definition">{escape(card.translation)}</div>
</div>
<div class="section">
  <h4>Example</h4>
  <div class="definition">{escape(card.example_sentence)}</div>
  <div class="subtle">{escape(card.example_translation)}</div>
</div>
<div class="section">
  <h4>Synonyms</h4>
  {_list_items(card.synonyms)}
</div>
<div class="section">
  <h4>Antonyms</h4>
  {_list_items(card.antonyms)}
</div>
<div class="section">
  <h4>Collocations</h4>
  {_list_items(card.collocations)}
</div>
<div class="section">
  <h4>Memory Tip</h4>
  <div class="definition">{memory_tip}</div>
</div>
</div>"""

