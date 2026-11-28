"""Chinese books (D-042, D-043, D-044): language detection, cleaning, sentence splitting, voices, and the server.
IDs refer to desktop/docs/test-cases.md (ZH-xx). All Chinese text here is written for these tests (D-014)."""
import pytest

from desktop.core.language import check_language, detect_language
from desktop.core.normalize import _is_title_page, _key, _plausible_title, _unlabel, normalize
from desktop.core.parse import Book, Chapter, load_book, unwrap
from desktop.core.segment import MAX_CHARS_ZH, split_paragraph, split_text
from desktop.server import service
from desktop.tts import kokoro, models
from tests.epub_factory import Page, Spec, build_epub
from tests.test_language import EN, book
from tests.test_server import V1, _upload, _wait, api  # noqa: F401 - api is a fixture

ZH = "河水静静地流过老磨坊，清晨的阳光渐渐变暖。老磨坊主每天都很早起床，去看看水车是否还在转动。他说：“水会记得一切。”"
ZH_HANT = "河水靜靜地流過老磨坊，清晨的陽光漸漸變暖。老磨坊主每天都很早起床，去看看水車是否還在轉動。他說：「水會記得一切。」"
JA = "川は古い水車小屋のそばを静かに流れていました。朝の光はだんだん暖かくなりました。粉屋は毎朝早く起きました。"


def p(text=ZH, n=2):
    return "<p>" + text * n + "</p>"


# ---------------------------------------------------------------- language

@pytest.mark.parametrize("text", [ZH, ZH_HANT])
def test_zh01_chinese_detected(text):
    assert detect_language(book(text * 4)) == "zh"
    assert check_language(book(text * 4)) == "zh"


def test_zh01_english_still_english():
    assert check_language(book(EN * 6)) == "en"
    # an English book that quotes a little Chinese stays English
    assert detect_language(book(EN * 6 + "他说：“水会记得一切。”")) == "en"


def test_zh02_japanese_refused():
    with pytest.raises(ValueError, match="English or Chinese"):
        check_language(book(JA * 6, language="ja"))


def test_zh02_too_little_text_follows_the_metadata():
    assert detect_language(book("短。", chapters=1, language="zh-TW")) == "zh"
    assert detect_language(book("Short.", chapters=1)) == "en"


# ---------------------------------------------------------------- cleaning

def zh_book_spec() -> Spec:
    """Like real Chinese EPUBs: title page, copyright page, preface, a part title that shares its file with the first
    chapter (上篇 + 第一章), a second chapter in its own file with sections, references at the end."""
    return Spec(
        title="磨坊之书：一个副标题", language="zh", pages=[
            Page("Text/p0.xhtml", "<p>磨坊之书</p><p>无名氏 著</p><p>某某出版社</p>", allow_short=True),
            Page("Text/p1.xhtml", "<p>图书在版编目（CIP）数据 磨坊之书 / 无名氏著. ISBN 000-0-000-00000-0 版权所有，侵权必究。</p>"),
            Page("Text/p2.xhtml", "<h1>自序 写在前面</h1>" + p()),
            Page("Text/p3.xhtml", '<h1>上篇 河流</h1><h2 id="c1">第一章 早晨</h2><h3 id="s1">第一节 水车</h3>' + p()
                 + '<h3 id="s2">第二节 阳光</h3>' + p()),
            Page("Text/p4.xhtml", '<h2>第二章 磨坊</h2><h3 id="s3">第一节 石磨</h3>' + p()),
            Page("Text/p5.xhtml", "<h1>参考文献</h1><p>[1] 无名氏. 河流简史[M]. 某地：某出版社，2000.</p>" + p(n=1)),
        ],
        toc_tree=[
            ("Text/p0.xhtml", "扉页", []),
            ("Text/p1.xhtml", "版权信息", []),
            ("Text/p2.xhtml", "自序 写在前面", []),
            ("Text/p3.xhtml", "上篇 河流", [
                ("Text/p3.xhtml#c1", "第一章 早晨", [("Text/p3.xhtml#s1", "第一节 水车", []),
                                                    ("Text/p3.xhtml#s2", "第二节 阳光", [])]),
                ("Text/p4.xhtml", "第二章 磨坊", [("Text/p4.xhtml#s3", "第一节 石磨", [])]),
            ]),
            ("Text/p5.xhtml", "参考文献", []),
        ])


def test_zh03_chinese_book_cleaned(tmp_path):
    out, report = normalize(build_epub(tmp_path / "zh.epub", zh_book_spec()))
    got = {c.title: c.text for c in load_book(out).chapters}
    assert list(got) == ["自序 写在前面", "第一章 早晨", "第二章 磨坊"]
    assert got["第一章 早晨"].startswith("上篇 河流\n第一章 早晨\n第一节 水车")  # the part title read with it
    assert "第二节 阳光" in got["第一章 早晨"] and "第一节 石磨" in got["第二章 磨坊"]  # sections stay inside
    reasons = [r for r, _ in report.removed]
    assert "front matter: 版权信息" in reasons and "back matter: 参考文献" in reasons
    assert report.language == "zh" and "Language: Chinese" in report.render()
    assert load_book(out).language == "zh"


def test_zh04_chapter_labels_and_titles():
    assert _unlabel(_key("第一章 早晨")) == _unlabel(_key("第1章 早晨")) == "早晨"
    assert _unlabel(_key("第十二节 阳光")) == "阳光"
    assert _plausible_title("序") and _plausible_title("自序 写在前面")
    assert not _plausible_title("a")


def test_zh04_title_page_and_colophon_removed():
    title = "磨坊之书：一个副标题"
    assert _is_title_page(Chapter("磨坊之书", "磨坊之书\n无名氏 著"), title)
    assert not _is_title_page(Chapter("磨坊之书", ZH * 40), title)  # a long chapter named like the book stays
    assert not _is_title_page(Chapter("第一章 早晨", "短"), title)


def test_zh05_txt_in_gb18030_one_paragraph_per_line(tmp_path):
    text = "\n".join(["第一章 早晨", ZH, ZH, "第二章 磨坊", ZH, "后记", ZH])
    src = tmp_path / "zh.txt"
    src.write_bytes(text.encode("gb18030"))
    b = load_book(src)
    assert [c.title for c in b.chapters] == ["第一章 早晨", "第二章 磨坊", "后记"]
    assert b.chapters[0].text.split("\n") == ["第一章 早晨", ZH, ZH]


def test_zh05_hard_wraps_joined_without_spaces():
    assert unwrap("河水静静地流过\n老磨坊。") == "河水静静地流过老磨坊。"
    assert unwrap("Hello\nworld") == "Hello world"
    assert unwrap("河水流过\nthe mill") == "河水流过 the mill"


# ---------------------------------------------------------------- sentences

def test_zh06_sentences_keep_their_closing_quotes():
    assert split_paragraph("他说：“我们走吧。”然后就走了。你呢？真的吗！好……再见。", "zh") == [
        "他说：“我们走吧。”", "然后就走了。", "你呢？", "真的吗！", "好……再见。"]
    assert split_paragraph("「我们走吧。」他说。", "zh") == ["「我们走吧。」", "他说。"]


def test_zh06_cut_inside_a_title_joins_back():
    assert split_paragraph("你读过《都要玩！：一个副标题》吗？读过。", "zh") == ["你读过《都要玩！：一个副标题》吗？", "读过。"]


def test_zh06_long_sentence_split_at_chinese_commas():
    long = "，".join(["河水静静地流过老磨坊"] * 30) + "。"
    parts = split_paragraph(long, "zh")
    assert len(parts) > 1 and all(len(s) <= MAX_CHARS_ZH for s in parts)
    assert "".join(parts) == long
    assert split_text(f"{ZH}\n{ZH}", "zh")[1][0].startswith("河水")


def test_zh06_english_splitting_unchanged():
    assert split_paragraph("One. Two.") == ["One.", "Two."]


# ---------------------------------------------------------------- voices

def test_zh07_voices_by_language(monkeypatch):
    assert kokoro.voice_language("zf_xiaoxiao") == "zh" and kokoro.voice_language("bm_george") == "en"
    assert kokoro.voice_for("bm_george", "zh") == "zf_xiaoxiao"  # English voice, Chinese book
    assert kokoro.voice_for("zm_yunxi", "zh") == "zm_yunxi"
    assert kokoro.voices("zh") == kokoro.V10_VOICES["zh"]
    monkeypatch.setattr(kokoro, "zh_installed", lambda: True)  # Kokoro v1.1-zh installed (D-044)
    assert kokoro.voices("zh") == models.ZH_VOICES and kokoro.voices("en") == kokoro.V10_VOICES["en"]
    assert kokoro.default_voice("zh") == "zf_001" and kokoro.voice_for("af_heart", "zh") == "zf_001"
    assert models.repo_of("zf_001") == models.ZH_REPO and models.repo_of("zf_xiaoxiao") == models.V10_REPO


# ---------------------------------------------------------------- server

def test_zh08_info_lists_voices_by_language(api):  # noqa: F811
    info = api.get(f"{V1}/info").json()
    langs = {l["code"]: l for l in info["languages"]}
    assert list(langs) == ["en", "zh"]
    assert langs["zh"]["default_voice"] == "zf_xiaoxiao" and "zm_yunxi" in langs["zh"]["voices"]
    assert set(info["voices"]) == {v for l in info["languages"] for v in l["voices"]}  # the flat list stays


def test_zh09_english_voice_gives_way_for_a_chinese_book(api):  # noqa: F811
    text = "\n\n".join(["第一章 早晨", ZH * 3, "第二章 磨坊", ZH * 3])
    draft_id = _upload(api, "zh.txt", text.encode("utf-8"), voice="af_heart")
    d = _wait(api, draft_id, "review", "error")
    assert d["status"] == "review" and d["report"]["language"] == "zh"
    r = api.post(f"{V1}/drafts/{draft_id}/approve", json={"voice": "af_heart"})
    assert r.status_code == 200
    assert api.get(f"{V1}/jobs/{r.json()['job_id']}").json()["voice"] == "zf_xiaoxiao"
    d = _wait(api, draft_id, "done", "review")
    b = api.get(f"{V1}/books/{d['book_id']}").json()
    assert b["language"] == "zh" and b["voice"] == "zf_xiaoxiao"
    assert all(c["voice"] == "zf_xiaoxiao" for c in b["chapters"])
    assert b["chapters"][0]["sentences"][1]["text"] == "河水静静地流过老磨坊，清晨的阳光渐渐变暖。"


def test_zh10_chinese_voice_sample_reads_chinese(api):  # noqa: F811
    assert api.get(f"{V1}/voices/zf_xiaoxiao/sample").status_code == 200
    assert service.jobs.tts.calls[-1] == ("zf_xiaoxiao", service.SAMPLE_TEXTS["zh"])
    assert api.get(f"{V1}/voices/zf_001/sample").status_code == 404  # v1.1-zh is not installed


class FakeZhModel:
    def __init__(self):
        self.installed, self.installing = False, False

    def status(self):
        return {"id": "kokoro-v1.1-zh", "installed": self.installed, "installing": self.installing,
                "done_bytes": 0, "total_bytes": models.ZH_SIZE, "error": None}

    def install(self):
        self.installed = True

    def remove(self):
        self.installed = False


def test_zh11_install_and_remove_the_zh_model(api, monkeypatch):  # noqa: F811
    fake, unloaded = FakeZhModel(), []
    monkeypatch.setattr(service, "zh_model", fake)
    monkeypatch.setattr(service.jobs.tts, "unload", unloaded.append, raising=False)
    assert api.get(f"{V1}/models/zh").json()["installed"] is False
    assert api.post(f"{V1}/models/zh").json()["installed"] is True
    # refused while a conversion uses one of its voices
    service.jobs.jobs["x"] = {"status": "running", "voice": "zf_001"}
    r = api.delete(f"{V1}/models/zh")
    assert r.status_code == 409 and "cancel it first" in r.json()["detail"]
    service.jobs.jobs["x"]["status"] = "done"
    assert api.delete(f"{V1}/models/zh").json()["installed"] is False
    assert unloaded == [models.ZH_REPO]  # the loaded copy leaves the GPU
