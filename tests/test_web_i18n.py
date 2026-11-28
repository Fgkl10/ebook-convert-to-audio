"""The web page's languages (D-040): English, Simplified and Traditional Chinese in desktop/web/i18n/."""
import json
import re

import pytest

from desktop import PROJECT

WEB = PROJECT / "desktop" / "web"
LANGS = ("en", "zh-Hans", "zh-Hant")


def _strings(lang: str) -> dict[str, str]:
    return json.loads((WEB / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_i18n01_every_language_has_the_same_keys():
    en = _strings("en")
    for lang in LANGS[1:]:
        other = _strings(lang)
        assert set(other) == set(en), (lang, set(en) ^ set(other))
        for key, text in other.items():
            assert text.strip(), (lang, key)
            assert _placeholders(text) == _placeholders(en[key]), (lang, key)


def test_i18n02_page_and_script_use_only_known_keys():
    en = _strings("en")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    html_keys = set(re.findall(r'data-i18n(?:-html|-title|-placeholder|-aria)?="([\w.]+)"', html))
    js_keys = set(re.findall(r"\bt\('([\w.]+)'", js)) | set(re.findall(r"'(review\.approve_(?:one|many))'", js))
    assert html_keys and js_keys
    assert html_keys <= set(en), html_keys - set(en)
    assert js_keys <= set(en), js_keys - set(en)
    unused = set(en) - html_keys - js_keys
    assert not unused, unused  # a key nothing shows is a translation nobody checks


@pytest.mark.parametrize("lang", LANGS)
def test_i18n03_served_as_static_files(api, lang):  # noqa: F811
    r = api.get(f"/static/i18n/{lang}.json")
    assert r.status_code == 200 and "json" in r.headers["content-type"]
    assert r.json()["app.name"]


def test_i18n04_language_choice_follows_the_browser():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "const LANGS = ['en', 'zh-Hans', 'zh-Hant'];" in js
    # zh-TW / zh-HK / zh-MO / zh-Hant → Traditional, any other zh → Simplified; a saved choice wins
    assert "/hant|-tw|-hk|-mo/.test(x) ? 'zh-Hant' : 'zh-Hans'" in js
    assert "localStorage.getItem('ebookAudioLang')" in js
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for lang in LANGS:
        assert f'data-lang="{lang}"' in html


from tests.test_server import api  # noqa: E402,F401 - api is a fixture
