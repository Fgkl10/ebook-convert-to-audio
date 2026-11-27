"""LAN server: one process holding the backend (desktop/service.py), its JSON API (desktop/api.py, under /api/v1)
and the web page (desktop/static/, plain files that only call the API). D-032.

Run:  .venv\\Scripts\\python -m desktop.server [--port 8000]
Then open http://localhost:8000 on the PC, or the printed LAN address on the phone. API docs: /docs.
"""
from __future__ import annotations

import argparse
import socket
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import service
from .api import API_VERSION, PREFIX, lan_ip, router, service_error

STATIC = Path(__file__).resolve().parent / "static"
SERVICE_TYPE = "_ebookaudio._tcp.local."

app = FastAPI(title="Ebook Audio Server", version=f"{API_VERSION}",
              description="Ebook to audiobook conversion. Clients use only the JSON API under " + PREFIX + ".")
app.state.port = 8000
app.include_router(router)
app.add_exception_handler(service.ServiceError, service_error)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- mDNS

def advertise(port: int):
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        return None
    ip = lan_ip()
    host = socket.gethostname()
    zc = Zeroconf()
    svc = ServiceInfo(
        SERVICE_TYPE, f"{host}.{SERVICE_TYPE}", addresses=[socket.inet_aton(ip)], port=port,
        properties={"path": PREFIX, "name": host}, server=f"{host}.local.",
    )
    try:
        zc.register_service(svc)
    except Exception as e:  # noqa: BLE001 - discovery is optional
        print(f"mDNS advertise failed ({e}); enter the address manually on the phone.")
        zc.close()
        return None
    return zc, svc


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    app.state.port = args.port
    service.LIBRARY.mkdir(parents=True, exist_ok=True)

    adv = advertise(args.port)
    print(f"\n  Ebook Audio Server\n  On this PC:   http://localhost:{args.port}\n"
          f"  On the phone: http://{lan_ip()}:{args.port}\n  API docs:     http://localhost:{args.port}/docs\n"
          f"  Data folder:  {service.LIBRARY.parent}\n")
    try:
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
    finally:
        if adv:
            zc, svc = adv
            zc.unregister_service(svc)
            zc.close()


if __name__ == "__main__":
    main()
