from __future__ import annotations

from html import escape
from typing import Dict, Iterable, List

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


def _wrap_card(html_body: str, preset_name: str) -> str:
    preset = _preset(preset_name)
    return f"""<div class="card">
<style>
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
.accent {{
    color: {preset["accent"]};
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
    line-height: 1.6;
}}
.section h4 {{
    margin: 0 0 6px;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {preset["accent"]};
}}
.sense {{
    margin-bottom: 12px;
}}
.sense:last-child {{
    margin-bottom: 0;
}}
.sense .label {{
    font-weight: 700;
}}
.sense .definition {{
    font-weight: 700;
}}
.sense .example {{
    margin-top: 4px;
}}
.sense .meaning {{
    margin-top: 2px;
}}
.entry {{
    margin-bottom: 8px;
}}
.entry:last-child {{
    margin-bottom: 0;
}}
ul {{
    margin: 6px 0 0 20px;
    padding: 0;
}}
</style>
{html_body}
</div>"""


def _render_meaning_html(entry) -> str:
    pos = escape(entry.part_of_speech or "")
    definition = escape(entry.definition)
    example_sentence = escape(entry.example_sentence or "")
    example_meaning = escape(entry.meaning or "")
    return f"""<div class="sense">
<div><strong>{pos}</strong>  <strong>{definition}</strong><br>
e.g. {example_sentence}<br>
 Meaning: {example_meaning}</div>
</div>"""


def _render_collocation_html(entry) -> str:
    phrase = escape(entry.phrase)
    gloss = escape(entry.gloss or "")
    if gloss:
        return f"<div class=\"entry\"><strong>{phrase}</strong>  {gloss}</div>"
    return f"<div class=\"entry\"><strong>{phrase}</strong></div>"


def _render_example_html(entry) -> str:
    sentence = escape(entry.sentence)
    meaning = escape(entry.meaning or "")
    if meaning:
        return f"""<div class="entry">{sentence}<br>
 Meaning: {meaning}</div>"""
    return f"<div class=\"entry\">{sentence}</div>"


def render_front_html(card: VocabularyCardData, preset_name: str = "classic") -> str:
    body = f"""<h3>📌 <em><strong>{escape(card.word)}</strong></em></h3>
<div>IPA: <strong>/{escape(card.ipa)}/</strong><br>
Base form: <strong>{escape(card.base_form)}</strong><br>
Part of speech: <strong>{escape(card.part_of_speech)}</strong><br>
Register: <strong>{escape(card.register)}</strong><br>
Frequency/Use: <strong>{escape(card.frequency)}</strong></div>"""
    return _wrap_card(body, preset_name)


def render_back_html(card: VocabularyCardData, preset_name: str = "classic") -> str:
    meaning_html = "\n".join(_render_meaning_html(entry) for entry in card.meanings) or "<div class=\"entry\">None</div>"
    collocation_html = "\n".join(_render_collocation_html(entry) for entry in card.collocations) or "<div class=\"entry\">None</div>"
    example_html = "\n".join(_render_example_html(entry) for entry in card.extra_examples) or "<div class=\"entry\">None</div>"
    body = f"""<h2>📌 Meaning (English-English)</h2>
{meaning_html}
<h2>📌 Common collocations</h2>
{collocation_html}
<h2>📌 Extra examples</h2>
{example_html}"""
    return _wrap_card(body, preset_name)


def _join_lines(lines: Iterable[str]) -> str:
    return "\n".join(line for line in lines if line)


def render_front_preview_text(card: Dict[str, object]) -> str:
    lines: List[str] = [
        f"📌 {card.get('word', '')}",
        f"IPA: /{card.get('ipa', '')}/",
        f"Base form: {card.get('base_form', '')}",
        f"Part of speech: {card.get('part_of_speech', '')}",
        f"Register: {card.get('register', '')}",
        f"Frequency/Use: {card.get('frequency', '')}",
    ]
    return _join_lines(lines)


def render_back_preview_text(card: Dict[str, object]) -> str:
    lines: List[str] = ["📌 Meaning (English-English)"]
    meanings = card.get("meanings", [])
    for meaning in meanings if isinstance(meanings, list) else []:
        if not isinstance(meaning, dict):
            continue
        pos = meaning.get("part_of_speech", "")
        definition = meaning.get("definition", "")
        example_sentence = meaning.get("example_sentence", "")
        example_meaning = meaning.get("meaning", "")
        lines.append(f"{pos} {definition}".strip())
        if example_sentence:
            lines.append(f"e.g. {example_sentence}")
        if example_meaning:
            lines.append(f"Meaning: {example_meaning}")
        lines.append("")

    lines.append("📌 Common collocations")
    collocations = card.get("collocations", [])
    for collocation in collocations if isinstance(collocations, list) else []:
        if not isinstance(collocation, dict):
            continue
        phrase = collocation.get("phrase", "")
        gloss = collocation.get("gloss", "")
        lines.append(f"{phrase}  {gloss}".strip())

    lines.append("")
    lines.append("📌 Extra examples")
    examples = card.get("extra_examples", [])
    for example in examples if isinstance(examples, list) else []:
        if not isinstance(example, dict):
            continue
        sentence = example.get("sentence", "")
        meaning = example.get("meaning", "")
        lines.append(sentence)
        if meaning:
            lines.append(f"Meaning: {meaning}")
        lines.append("")

    return "\n".join(line for line in lines if line is not None).strip()
