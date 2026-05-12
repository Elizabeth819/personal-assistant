# Architecture

`personal-assistant` is built as three vertical layers, each replaceable:

```
┌────────────────────────────────────────────┐
│  L3 Memory     — what the assistant knows   │  src/pa/memory + ingest/
│  L2 Core/API   — orchestration & contracts  │  src/pa/core, src/pa/api
│  L1 Executor   — device-side action layer   │  src/pa/executor + adapters/
└────────────────────────────────────────────┘
```

## Layers

- **Memory (L3)** — claude-mem is the primary store today; `pa.memory` provides
  a project-local interface and will grow a query/RAG surface on top.
- **Core / API (L2)** — `pa.core` holds config + logging primitives; `pa.api`
  exposes a small FastAPI surface (`/memory`, `/execute`, `/health`). The CLI
  (`pa`) wraps the same primitives for terminal use.
- **Executor (L1)** — `pa.executor.base` defines the `Action` / `ActionResult`
  contract. Adapters under `pa.adapters` implement it for concrete targets
  (echo, iOS Shortcuts, Tasker, WeChat gateway, browser).

## Why this split

- Memory is the moat. Execution is a commodity — keep it pluggable.
- Tests pin the contract at L1/L2; adapters can be swapped without touching
  callers.
- The HTTP API is the integration boundary for any device-side runtime
  (mobile bot, shortcut, browser extension).

## Adding an adapter

1. Subclass `pa.executor.base.Executor`, set `target`, implement `execute`.
2. Register it in `pa/api/routes.py` (or a future `executor.registry`).
3. Add unit + integration tests under `tests/`.
