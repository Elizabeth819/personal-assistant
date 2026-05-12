"""FastAPI app entrypoint."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pa import __version__
from pa.api.routes import router
from pa.core import get_logger, get_settings, setup_logging

_STATIC = Path(__file__).parent / "static"
_log = get_logger(__name__)


def _lan_ip() -> str:
    """Best-effort LAN IPv4 — prefer Wi-Fi (en0/en1) over VPN tun interfaces."""
    import subprocess
    for iface in ("en0", "en1"):
        try:
            out = subprocess.check_output(
                ["ipconfig", "getifaddr", iface], text=True, timeout=2
            ).strip()
            if out and not out.startswith("169.254"):
                return out
        except Exception:
            continue
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    s = get_settings()
    zc = info = None
    try:
        from zeroconf import IPVersion, ServiceInfo, Zeroconf
        ip = _lan_ip()
        zc = Zeroconf(ip_version=IPVersion.V4Only)
        info = ServiceInfo(
            type_="_http._tcp.local.",
            name="pa._http._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=s.port,
            server="pa-agent.local.",
            properties={"path": "/"},
        )
        zc.register_service(info, cooperating_responders=True)
        _log.info("mdns.registered", host="pa-agent.local", ip=ip, port=s.port)
    except Exception as exc:
        _log.warning("mdns.skipped", err=str(exc))
    try:
        yield
    finally:
        try:
            if zc and info:
                zc.unregister_service(info)
                zc.close()
        except Exception:
            pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Personal Assistant",
        version=__version__,
        debug=settings.env == "dev",
        lifespan=lifespan,
    )
    app.include_router(router)
    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(str(_STATIC / "index.html"))

    return app


app = create_app()
