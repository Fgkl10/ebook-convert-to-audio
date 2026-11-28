"""Pairing a phone (D-037): which addresses the PC offers, QR codes, typed addresses, and the token that guards
/api/v1 from other devices. IDs refer to desktop/docs/test-cases.md (NET-xx, AUTH-xx)."""
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from desktop.server import app as server
from desktop.server import auth, network
from tests.test_api import AUDIO, _write_book
from tests.test_server import V1, api  # noqa: F401 - api is a fixture

ADAPTERS = [
    NS(nice_name="Intel(R) Wi-Fi 6E AX211 160MHz", ips=[NS(ip="192.168.24.154"), NS(ip=("fe80::1", 0, 18))]),
    NS(nice_name="ZeroTier Virtual Port", ips=[NS(ip="10.251.93.75")]),
    NS(nice_name="Software Loopback Interface 1", ips=[NS(ip="127.0.0.1")]),
    NS(nice_name="Ethernet", ips=[NS(ip="169.254.10.2")]),  # link-local: no DHCP answer
]


@pytest.fixture
def adapters(monkeypatch):
    monkeypatch.setattr("ifaddr.get_adapters", lambda: ADAPTERS)
    monkeypatch.setattr(network, "default_route_address", lambda: "192.168.24.154")
    monkeypatch.delenv(network.ADVERTISE_ENV, raising=False)


def remote(app=server.app, host="10.251.93.9"):
    """A client on another device (a phone over ZeroTier), not the PC itself."""
    return TestClient(app, client=(host, 5000))


# ---------------------------------------------------------------- addresses

def test_net01_local_address_first_then_the_others(adapters, monkeypatch):
    got = network.phone_addresses()
    assert got == [{"address": "192.168.24.154", "adapter": "Intel(R) Wi-Fi 6E AX211 160MHz"},
                   {"address": "10.251.93.75", "adapter": "ZeroTier Virtual Port"}]  # no loopback/link-local/IPv6
    assert network.phone_addresses("10.251.93.75")[0] == {"address": "10.251.93.75", "adapter": "ZeroTier Virtual Port"}
    monkeypatch.setenv(network.ADVERTISE_ENV, "my-pc.example")
    assert [a["address"] for a in network.phone_addresses()] == ["my-pc.example", "192.168.24.154", "10.251.93.75"]


def test_net02_info_lists_every_address_with_its_own_qr(api, adapters):  # noqa: F811
    info = api.get(f"{V1}/info").json()
    port, token = server.app.state.port, auth.token()
    assert [(u["address"], u["adapter"]) for u in info["urls"]] == [
        ("192.168.24.154", "Intel(R) Wi-Fi 6E AX211 160MHz"), ("10.251.93.75", "ZeroTier Virtual Port")]
    assert info["url"] == f"http://192.168.24.154:{port}" and info["qr_svg"] == info["urls"][0]["qr_svg"]
    for u in info["urls"]:
        assert u["url"] == f"http://{u['address']}:{port}"
        assert u["pair_url"] == f"{u['url']}/#token={token}"
        assert u["qr_svg"].startswith("<svg") and u["qr_svg"] == network.qr_svg(u["pair_url"])
    assert info["urls"][0]["qr_svg"] != info["urls"][1]["qr_svg"]


def test_net03_typed_address_gets_a_qr(api):  # noqa: F811
    port, token = server.app.state.port, auth.token()
    for typed, url in (("10.251.93.75", f"http://10.251.93.75:{port}"), (" my-pc.example:9000 ", "http://my-pc.example:9000"),
                       ("[fe80::1]:8000", "http://[fe80::1]:8000")):
        r = api.get(f"{V1}/qr", params={"address": typed})
        assert r.status_code == 200, (typed, r.text)
        body = r.json()
        assert body["url"] == url and body["pair_url"] == f"{url}/#token={token}" and body["adapter"] == "typed"
        assert body["qr_svg"] == network.qr_svg(body["pair_url"])
    for bad in ("http://x", "a b", "x:0", "x:70000", "x/y", "", "999.1.1.1", "[nope]", "-x.example"):
        r = api.get(f"{V1}/qr", params={"address": bad})
        assert r.status_code == 400 and isinstance(r.json()["detail"], str), bad
    assert api.get(f"{V1}/qr").status_code == 422  # address missing


# ---------------------------------------------------------------- token

def test_auth01_other_devices_need_the_token(api):  # noqa: F811
    phone, token = remote(), auth.token()
    r = phone.get(f"{V1}/books")
    assert r.status_code == 401 and r.json() == {"detail": auth.PAIR_MESSAGE}
    for path in ("/info", "/drafts", "/jobs", "/qr?address=10.0.0.1"):
        assert phone.get(V1 + path).status_code == 401, path
    assert phone.delete(f"{V1}/books/nope").status_code == 401  # refused before anything else happens
    assert phone.get(f"{V1}/books", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert phone.get(f"{V1}/books", headers={"authorization": f"bearer {token}"}).status_code == 200
    assert phone.get(f"{V1}/books", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert phone.get(f"{V1}/books", params={"token": "wrong"}).status_code == 401
    d = _write_book("paired-0123abcd", "Paired", ["One"])
    url = f"{V1}/books/{d.name}/files/ch000.m4a"  # an <audio src> can only carry the token in the URL
    assert phone.get(url).status_code == 401
    r = phone.get(url, params={"token": token})
    assert r.status_code == 200 and r.content == AUDIO
    part = phone.get(url, params={"token": token}, headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == AUDIO[:10]


def test_auth02_the_pc_itself_and_the_page_need_none(api):  # noqa: F811
    assert api.get(f"{V1}/books").status_code == 200  # TestClient's own host stands for the PC's browser
    for host in ("127.0.0.1", "::1"):
        assert remote(host=host).get(f"{V1}/books", headers={"Host": "localhost:8000"}).status_code == 200, host
    for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000"):
        assert remote(host="127.0.0.1").get(f"{V1}/books", headers={"Host": host}).status_code == 200, host
    assert api.post(f"{V1}/jobs/nope/cancel", headers={"Origin": "http://localhost:8000"}).status_code == 404
    phone = remote()
    assert phone.get("/").status_code == 200 and phone.get("/static/app.js").status_code == 200
    assert phone.get("/openapi.json").status_code == 200  # the contract itself is public


def test_auth05_other_sites_in_the_pcs_browser_are_not_the_pc(api):  # noqa: F811
    """A web page open in the PC's browser reaches loopback too: by DNS rebinding (its own domain pointed at 127.0.0.1,
    so the Host is foreign) or by a cross-site request (a foreign Origin). Neither gets the PC's free pass."""
    pc = remote(host="127.0.0.1")
    r = pc.get(f"{V1}/info", headers={"Host": "evil.example:8000"})
    assert r.status_code == 401 and "token" not in r.text  # /info holds the token in its QR codes
    assert pc.post(f"{V1}/jobs/nope/cancel", headers={"Host": "localhost:8000", "Origin": "http://evil.example"}
                   ).status_code == 401
    assert api.post(f"{V1}/jobs/nope/cancel", headers={"Origin": "null"}).status_code == 401  # a sandboxed page
    token = auth.token()  # a paired phone's page is cross-origin to nothing: the token still works anywhere
    assert pc.get(f"{V1}/books", headers={"Host": "evil.example", "Authorization": f"Bearer {token}"}).status_code == 200


def test_auth03_token_is_kept_and_can_be_replaced(api):  # noqa: F811
    first = auth.token()
    assert len(first) >= 32 and auth.token_path().read_text(encoding="utf-8") == first
    auth._tokens.clear()  # a server restart
    assert auth.token() == first
    second = auth.token(new=True)
    assert second != first and auth.token_path().read_text(encoding="utf-8") == second
    phone = remote()
    assert phone.get(f"{V1}/books", headers={"Authorization": f"Bearer {first}"}).status_code == 401
    assert phone.get(f"{V1}/books", headers={"Authorization": f"Bearer {second}"}).status_code == 200


def test_auth04_page_sends_the_token(api):  # noqa: F811
    """The page keeps a token from #token=… and sends it: a header on fetch, ?token= on src/href URLs."""
    from tests.test_api import STATIC
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "#token=" in js and "Authorization" in js and "history.replaceState" in js
    for src in ("audio.src = tok(", "sampleAudio.src = tok(", 'src="${tok(', "href = tok(", 'href="${tok('):
        assert src in js, src
