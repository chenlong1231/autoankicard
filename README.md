# autoankicard

Windows desktop application for local AI vocabulary card generation for Anki.

## Current Scope

The desktop app now covers phase 1 through phase 3: core generation, preview, deck selection, tags, duplicate handling, retry/validation, batch generation, local history, template presets, and note model customization.

## What it does

- Runs as a Windows GUI app.
- Takes one English word or a batch of words.
- Calls SiliconFlow with `deepseek-ai/DeepSeek-V3.2`.
- Validates the LLM response as structured JSON.
- Renders deterministic Front and Back HTML in code using an English-English study-card format.
- Lets you translate first, then push the prepared card to Anki through AnkiConnect.
- Shows preview, raw JSON, returned note ID, and local history.

## Setup

Create a `.env` file in the project root:

```env
SILICONFLOW_API_KEY=your_api_key_here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3.2
DEFAULT_DECK=Default
NOTE_MODEL_NAME=Basic
TEMPLATE_PRESET=classic
DEFAULT_TAGS=
SKIP_DUPLICATES=true
TIMEOUT_SECONDS=60
RETRY_COUNT=2
RETRY_DELAY_SECONDS=1.5
```

If you need a template, copy `.env.example`.

## Run

```bash
python app.py
```

This is the development launch path. The intended product shape is a Windows desktop app, not a web app or browser-based tool.

## Workflow

1. Enter a word.
2. Click `Translate` to generate and preview the card.
3. Click `Push to Anki` to send the prepared note into Anki.

## Notes

- `.env` stays local and is ignored by git.
- `.autoankicard.log` is created locally and is ignored by git.
- The app does not generate HTML from the model output. It validates JSON first, then renders HTML deterministically in Python.
- You may need to create or choose an Anki note model whose field names match the settings in the app.
- If AnkiConnect is not running, deck/model refresh and note submission will fail until Anki is open with AnkiConnect enabled.
