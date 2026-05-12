# personal-assistant

A personal AI assistant: **long-term memory + multi-device executor**.

## Layout

```
src/pa/
  core/        # config, logging
  memory/      # memory store (bridges claude-mem; project-local API)
  executor/    # device-agnostic Action/Result contract
  adapters/    # concrete executors (echo, ios, android, web, ...)
  api/         # FastAPI surface
  cli.py       # `pa` Typer CLI
tests/         # unit + integration
ingest/        # Phase 1 — knowledge ingestion pipeline (legacy)
docs/          # ARCHITECTURE.md
```

## Quickstart

```bash
./scripts/bootstrap.sh    # install deps + pre-commit + .env
make test                 # run tests
make run                  # API on :8765
uv run pa info            # show resolved config
```

## Make targets

`install`, `dev`, `fmt`, `lint`, `type`, `test`, `cov`, `run`, `cli`, `hooks`, `clean`.

## Architecture

See `docs/ARCHITECTURE.md`. Three layers:
- **L3 Memory** — what the assistant knows
- **L2 Core/API** — orchestration & contracts
- **L1 Executor** — device-side adapters

## Phase 1 — knowledge ingestion (legacy pipeline)

```bash
$EDITOR ingest/sources.txt          # whitelist
./ingest/scan.sh                    # scan -> manifests/files.tsv
./ingest/batch.sh 50                # split into batches
./ingest/run_batch.sh 0 9           # headless ingest with claude (needs copilot-api :4142)
```

claude-mem stores at `~/.claude/plugins/data/claude-mem-thedotmack`; observations
UI at `http://localhost:37701`.

### Maintenance

```bash
tar -czf snapshots/claude-mem-$(date +%Y%m%d).tgz \
  -C ~/.claude/plugins/data claude-mem-thedotmack
```

### Safety notes

- `scan.sh` excludes `*.key`, `*.pem`, `*.env`, `id_rsa*`, and cache dirs.
- Before large batches: `head manifests/files.tsv` to sanity-check inclusions.
- Keep private third-party content (chats, contracts) in a separate whitelist.
