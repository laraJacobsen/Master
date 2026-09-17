# Frontend -- React + TypeScript (Vite)

Same three pages as before, same URLs, same behavior -- just React/TS
instead of plain HTML/JS. Each page is its own Vite entry point (not a
client-routed SPA), so `setup.html` / `student.html` / `lecturer.html` and
their `?question_id=` links work exactly as before.

```
setup.html, student.html, lecturer.html   Vite entry points (HTML shells)
src/setup/, src/student/, src/lecturer/   One React root + styles per page
src/shared/types.ts                        TS types for the API's JSON shapes
src/shared/api.ts                          fetch() wrappers used by all three pages
```

## Build

```bash
npm install
npm run build       # type-checks, then builds to dist/
```

`backend/main.py` serves `frontend/dist/` as static files, so the backend
needs a build to exist before it has anything to serve at `/setup.html` etc.

## Dev server

```bash
npm run dev
```

Runs on Vite's dev server (default `http://localhost:5173`) with hot reload.
`fetch("/api/...")` calls are proxied to `http://localhost:8000` (see
`vite.config.ts`), so run the FastAPI backend alongside it as usual.
