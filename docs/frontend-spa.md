# Frontend SPA (React)

A modern single-page interface served at `/` (redirects to `/ui`).

## Develop
```bash
cd frontend
npm install
npm run dev        # Vite on http://localhost:5173, proxies /api to :8765
# in another terminal:
.venv/bin/python -m meeting_processor web
```

## Build for normal use
```bash
cd frontend && npm run build      # outputs to meeting_processor/web/spa/
.venv/bin/python -m meeting_processor web   # serves the SPA at http://127.0.0.1:8765/
```

If the SPA build is absent, `/` falls back to the classic HTMX UI at `/dashboard`.
