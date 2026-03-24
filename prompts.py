from __future__ import annotations


SYSTEM_PROMPT = """You generate study-card data for English vocabulary.
Return exactly one JSON object and nothing else.
Do not wrap the JSON in markdown fences.
Do not invent HTML.
Do not add commentary.
"""


def build_user_prompt(word: str) -> str:
    return f"""Create a vocabulary card for the English word: {word}

Return a single JSON object with these keys:
- word: the normalized word
- phonetic: IPA transcription, or an empty string if uncertain
- part_of_speech: a short label such as noun, verb, adjective, adverb, or phrase
- definition: a concise English definition
- translation: a Simplified Chinese translation
- example_sentence: one natural English example sentence
- example_translation: a Simplified Chinese translation of the example
- synonyms: array of short English synonyms
- antonyms: array of short English antonyms
- collocations: array of useful collocations or common phrases
- memory_tip: one short memory aid in English or Chinese

Constraints:
- Keep the definition stable and concise.
- Keep the example natural and easy to study.
- Output JSON only.
"""

