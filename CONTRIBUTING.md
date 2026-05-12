# Contributing

Thanks for your interest! This project is built in the open and PRs are welcome.

## Dev setup

```bash
./scripts/bootstrap.sh
cp .env.example .env  # fill in Azure OpenAI keys
make test
```

## Before opening a PR

```bash
make fmt lint type test
```

All three must pass. CI runs the same on every PR.

## Adding a new in-app deeplink

1. Add a tuple to `_SEARCH_DEEPLINKS` in `src/pa/agent/intent.py`
   ```python
   (("应用别名",), "scheme://search?q={q}", "应用展示名"),
   ```
2. Add a unit test in `tests/unit/test_intent.py`.
3. Verify on a real device (or document the deeplink source).

## Adding a new device adapter (Android, web, …)

Implement the `Executor` protocol in `src/pa/adapters/<name>.py`, then wire
it into `src/pa/api/routes.py` behind a settings flag. Keep the existing
`Action`/`ActionResult` contract in `src/pa/executor/base.py`.

## Code style

- Ruff for format + lint, mypy strict-ish.
- Type-hint everything new.
- No trailing comments explaining *what* — comment *why* only when non-obvious.
- Tests next to the feature (`tests/unit/test_<module>.py`).
