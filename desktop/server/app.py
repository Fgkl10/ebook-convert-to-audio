"""LAN server: one process holding the backend (service.py), its JSON API (api.py, under /api/v1) and the web page
(desktop/web/, plain files that only call the API, served at /static). D-032, D-033.

Run:  ebook-server [--port 8000]      (or: python -m desktop.server)
Then open http://localhost:8000 on the PC, or the printed LAN address on the phone. API docs: /docs.
"""
from __future__ import annotations

import argparse
import socket

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .. import PROJECT
from . import service
from . import auth, network
from .api import API_VERSION, PREFIX, router, service_error

STATIC = PROJECT / "desktop" / "web"
SERVICE_TYPE = "_ebookaudio._tcp.local."
SHUTDOWN_GRACE_S = 1  # seconds a Ctrl+C waits for open requests (downloads, page loads) before closing them

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

def _is_ipv4(text: str) -> bool:
    try:
        socket.inet_aton(text)
        return text.count(".") == 3
    except OSError:
        return False


def advertise(port: int, addresses: list[str]):
    """mDNS on every address (ZeroTier carries multicast too). The QR code stays the reliable way in."""
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        return None
    host = socket.gethostname()
    zc = Zeroconf()
    svc = ServiceInfo(
        SERVICE_TYPE, f"{host}.{SERVICE_TYPE}", addresses=[socket.inet_aton(ip) for ip in addresses], port=port,
        properties={"path": PREFIX, "name": host}, server=f"{host}.local.",
    )
    try:
        zc.register_service(svc)
    except Exception as e:  # noqa: BLE001 - discovery is optional
        print(f"mDNS advertise failed ({e}); scan the QR code on the page instead.")
        zc.close()
        return None
    return zc, svc


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--advertise", metavar="ADDRESS",
                    help=f"the address the QR code uses by default (also ${network.ADVERTISE_ENV}); "
                         "default: the local address. Any other address can be picked on the home page")
    ap.add_argument("--new-token", action="store_true",
                    help="make a new pairing token: every phone has to scan the QR code again")
    args = ap.parse_args()
    if args.advertise:
        try:
            host, port = network.parse_address(args.advertise, args.port)  # refuse a typo before starting
        except service.Invalid as e:
            ap.error(f"--advertise: {e}")
        if port != args.port:
            ap.error("--advertise takes an address without a port; the server's port is --port")
        args.advertise = host
    app.state.port, app.state.advertise = args.port, args.advertise
    service.LIBRARY.mkdir(parents=True, exist_ok=True)
    removed = service.clean_leftovers()
    if removed:
        print(f"  Removed {len(removed)} half-written file(s) left by an interrupted run.")
    auth.token(new=args.new_token)
    if args.new_token:
        print("  Made a new pairing token: scan the QR code again on every phone.")

    addresses = network.phone_addresses(args.advertise)
    adv = advertise(args.port, [a["address"] for a in addresses if _is_ipv4(a["address"])])
    # No phone addresses here: a phone needs the token, which only the QR code on the page carries (D-037). The page
    # lists every address with its own QR code.
    print(f"\n  Ebook Audio Server\n  On this PC:   http://localhost:{args.port}\n"
          f"  Phone:        scan the QR code at http://localhost:{args.port}\n"
          f"  API docs:     http://localhost:{args.port}/docs\n"
          f"  Data folder:  {service.LIBRARY.parent}\n")
    try:
        # On Ctrl+C uvicorn waits for open connections to close; a phone downloading a chapter could hold it for
        # minutes. After SHUTDOWN_GRACE_S it cuts them off (an interrupted download resumes with HTTP Range).
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning",
                    timeout_graceful_shutdown=SHUTDOWN_GRACE_S)
    finally:
        if adv:
            zc, svc = adv
            zc.unregister_service(svc)
            zc.close()


if __name__ == "__main__":
    main()
