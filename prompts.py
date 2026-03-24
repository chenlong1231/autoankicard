from __future__ import annotations


SYSTEM_PROMPT = """You generate English-English vocabulary study cards.
Return exactly one JSON object and nothing else.
Do not wrap the JSON in markdown fences.
Do not invent HTML.
Do not add commentary.
Use English definitions and English explanations only.
"""


def build_user_prompt(word: str) -> str:
    return f"""Create a vocabulary card for the English word: {word}

Return a single JSON object with these keys:
- word: the normalized headword
- ipa: IPA transcription without surrounding slashes
- base_form: the lemma or base form
- part_of_speech: a short label such as n., v., adj., adv., or phrase
- register: a short label such as neutral, formal, informal, technical, or literary
- frequency: a short label such as common, less common, rare
- meanings: array of objects with:
  - part_of_speech
  - definition: an English-English explanation
  - example_sentence: one natural English example sentence
  - meaning: a short English explanation of the example
- collocations: array of objects with:
  - phrase
  - gloss: a short English explanation of the collocation
- extra_examples: array of objects with:
  - sentence
  - meaning: a short English explanation of the example

Constraints:
- Use English-English explanations only.
- Make the definitions concise but accurate.
- Prefer 1-3 meanings for the word.
- Include 3-8 useful collocations.
- Include 2-4 extra examples.
- Output JSON only.
"""
