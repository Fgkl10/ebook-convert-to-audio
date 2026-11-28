"""Which addresses a phone can reach this PC at, and the pairing QR codes for them (D-037). No HTTP in here.

The phone may connect over the local network or over a virtual network such as ZeroTier, so every IPv4 address of
the PC is offered. The default is the local address the PC uses for its default route; the web page lets the user
switch the QR code to any other address, or type one.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket

from .service import Invalid

ADVERTISE_ENV = "EBOOK_AUDIO_ADVERTISE"

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST_RE = re.compile(rf"{_LABEL}(?:\.{_LABEL})*")
_ADDRESS_RE = re.compile(r"(?:\[(?P<v6>[0-9A-Fa-f:.]+)\]|(?P<host>[A-Za-z0-9.-]+))(?::(?P<port>\d{1,5}))?")


def default_route_address() -> str:
    """The address of the interface the PC uses for its default route (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def all_addresses() -> list[dict]:
    """Every usable IPv4 address with its adapter's name, e.g. {"address": "10.251.93.75", "adapter": "ZeroTier
    Virtual Port"}. Loopback, link-local and unspecified addresses are left out."""
    try:
        import ifaddr  # installed with zeroconf

        adapters = ifaddr.get_adapters()
    except Exception:  # noqa: BLE001 - listing adapters is best effort
        adapters = []
    found, seen = [], set()
    for adapter in adapters:
        for ip in adapter.ips:
            if not isinstance(ip.ip, str):  # IPv6 entries are tuples
                continue
            addr = ipaddress.ip_address(ip.ip)
            if addr.is_loopback or addr.is_link_local or addr.is_unspecified or ip.ip in seen:
                continue
            seen.add(ip.ip)
            found.append({"address": ip.ip, "adapter": adapter.nice_name})
    return found


def preferred_address(override: str | None = None) -> str:
    """--advertise / EBOOK_AUDIO_ADVERTISE if given, else the local default-route address (as before D-037)."""
    return override or os.environ.get(ADVERTISE_ENV) or default_route_address()


def phone_addresses(override: str | None = None) -> list[dict]:
    """The preferred address first, then every other one; each {"address", "adapter"} ("" if unknown)."""
    first, found = preferred_address(override), all_addresses()
    adapter = next((a["adapter"] for a in found if a["address"] == first), "")
    return [{"address": first, "adapter": adapter}, *(a for a in found if a["address"] != first)]


def parse_address(text: str, default_port: int) -> tuple[str, int]:
    """A typed address: a host name, an IPv4 address or a bracketed IPv6 address, with an optional :port.
    Returns (host for a URL, port). Raises Invalid with a message for the user."""
    text = (text or "").strip()
    m = _ADDRESS_RE.fullmatch(text)
    bad = Invalid("Type an address like 10.251.93.75, my-pc.example or 10.251.93.75:8000 (no http://, no path)")
    if not m:
        raise bad
    port = int(m.group("port")) if m.group("port") else default_port
    if not 1 <= port <= 65535:
        raise Invalid(f"Port {port} is out of range (1-65535)")
    if m.group("v6"):
        try:
            ipaddress.IPv6Address(m.group("v6"))
        except ValueError:
            raise bad from None
        return f"[{m.group('v6')}]", port
    host = m.group("host")
    if re.fullmatch(r"[\d.]+", host):  # looks like IPv4: must be one
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            raise bad from None
    elif not _HOST_RE.fullmatch(host) or len(host) > 253:
        raise bad
    return host, port


def base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def pair_url(host: str, port: int, token: str) -> str:
    """What the QR code holds: the page, with the pairing token in the fragment (never sent to the server)."""
    return f"{base_url(host, port)}/#token={token}"


def qr_svg(text: str) -> str | None:
    try:
        import qrcode
        import qrcode.image.svg

        return qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).to_string(encoding="unicode")
    except Exception:  # noqa: BLE001 - the QR code is optional
        return None
