# AGENTS Instructions

## Runtime Rule for Codex

- Default execution path in this repository must prefer `uv`.
- For Python-related operations, use `uv run ...` first.
- Recommended commands:
  - Start app: `uv run uvicorn app.main:app --reload`
  - Run tests: `uv run pytest`
  - Run scripts: `uv run python <script.py>`
- If `uv` is unavailable, use existing alternatives as fallback.
