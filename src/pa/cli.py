"""Typer-based CLI."""

from __future__ import annotations

import typer
from rich.console import Console

from pa import __version__
from pa.core import get_settings, setup_logging

app = typer.Typer(no_args_is_help=True, add_completion=False, help="personal-assistant CLI")
console = Console()


@app.callback()
def main() -> None:
    setup_logging()


@app.command()
def version() -> None:
    """Print version."""
    console.print(f"pa {__version__}")


@app.command()
def info() -> None:
    """Show resolved settings."""
    s = get_settings()
    console.print_json(data=s.model_dump(mode="json"))


@app.command()
def serve(
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    reload: bool = typer.Option(False),
) -> None:
    """Run the API server."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "pa.api.app:app",
        host=host or s.host,
        port=port or s.port,
        reload=reload,
    )


@app.command()
def talk(no_voice: bool = typer.Option(False, "--no-voice", help="Disable TTS")) -> None:
    """Interactive REPL: type → Claude reply → spoken aloud (macOS `say`)."""
    from pa.agent import run_repl

    run_repl(voice=not no_voice)


if __name__ == "__main__":
    app()
