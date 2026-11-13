# CLAUDE.md

## Project
Learning Game: a system that uses AI to turn learning material into games for kids.
It finds out where each child struggles and reports to teachers and parents.

## Tech stack
- Backend: Python 3.12, FastAPI, Pydantic, pytest. Managed with uv.
- Frontend: React, TypeScript, Vite.
- AI: OpenAI API for the prototype, behind backend/app/llm.py so the provider can be swapped.

## How we work
- Show a plan before changing files. Wait for approval.
- Explain every change clearly: what you changed and why.
- Never run git commit, git push, or create branches. The developer does all git work.
- Write or update tests with every change. Run the tests after every change.
- Keep changes small: one task at a time. Ask before touching files outside the task.
- Never read, create, or change .env files or any secrets.

## Commands
- Run tests: `uv run pytest` (inside backend/)
- Lint: `uv run ruff check .` (inside backend/)
- Run the server locally: `uv run --env-file .env python -m fastapi dev app/api.py` (inside backend/).
  API docs at http://127.0.0.1:8000/docs
- Run the frontend dev server: `npm run dev` (inside frontend/).
  The app is at http://localhost:5173
- Run frontend tests: `npm test` (inside frontend/)
- Lint the frontend: `npm run lint` (inside frontend/)
- Build the frontend: `npm run build` (inside frontend/)
- Run both servers for local work (two terminals, backend first):
  1. Inside backend/: `uv run --env-file .env python -m fastapi dev app/api.py`
  2. Inside frontend/: `npm run dev`, then open http://localhost:5173
  The frontend calls `/api/...` and the Vite dev server forwards it to the backend
  at http://127.0.0.1:8000 (without the `/api` prefix).

## Code style
- Type hints on every function.
- Small, pure functions where possible.
- Names and comments in English.
- Do not write tests that only check the value of a constant.