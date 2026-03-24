# AGENTS.md

## Project
Windows desktop application for local AI vocabulary card generation for Anki.

## Goal
Generate stable vocabulary cards from a user-input English word in a Windows GUI app and send them directly to a locally running Anki instance through AnkiConnect.

## Current Milestone
Phase 1 through Phase 3 are in scope. Build and stabilize the Windows desktop workflow, then keep phase 2 and phase 3 features available in the app.

## Core Workflow
1. User inputs one English word.
2. The app calls an LLM API.
3. The LLM returns structured JSON only.
4. The app renders Front HTML and Back HTML from deterministic templates.
5. The app sends the note to AnkiConnect using addNote.
6. The app shows the generated card preview and the returned note ID.

## Architecture Rules
- Build a Windows desktop application, not a web app.
- Prefer a GUI executable-oriented workflow over script-only usage.
- Do not use CSV import as the primary path.
- Use AnkiConnect HTTP API.
- Keep concerns separated:
  - UI
  - LLM client
  - schema validation
  - HTML rendering
  - Anki client
- The LLM must not generate final HTML directly.
- Rendering logic must be deterministic and code-based.

## Required Modules
- app.py
- llm_client.py
- schema.py
- renderers.py
- anki_client.py
- prompts.py
- config.py

## Phase 1
- Build schema
- Build prompt
- Call LLM
- Validate JSON
- Render Front/Back HTML
- Send note to AnkiConnect
- Show success/error result

## Phase 2
- Add preview
- Add deck selection
- Add tags
- Add duplicate handling
- Add retry and validation

## Phase 3
- Add batch generation
- Add local history
- Add template presets
- Add note model customization

## Scope Rule
- Keep the app Windows-native and local.
- Avoid web UI and browser-hosted workflows.
