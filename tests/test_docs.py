"""The Mermaid diagrams in the docs avoid what breaks GitHub's renderer (DOC-01)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".venv", ".scratch", "node_modules", "build", ".git", ".gradle"}
ENTITY = re.compile(r"&#?\w+;")  # &lt; &amp; &#35; keep their semicolon


def mermaid_blocks():
    for md in sorted(ROOT.rglob("*.md")):
        if SKIP & set(md.relative_to(ROOT).parts):
            continue
        lines = md.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith("```mermaid"):
                start = i + 1
                j = start
                while not lines[j].strip().startswith("```"):
                    j += 1
                yield md.relative_to(ROOT), start, lines[start:j]
                i = j
            i += 1


def test_doc01_mermaid_text_has_no_statement_breakers():
    blocks = list(mermaid_blocks())
    assert len(blocks) >= 20  # the docs and the three READMEs
    bad = []
    for md, start, lines in blocks:
        kind = lines[0].strip().split()[0]
        for k, line in enumerate(lines, 1):
            # ';' ends a statement: in a sequence diagram's message it cuts the line and breaks the parse
            if ";" in ENTITY.sub("", line):
                bad.append(f"{md}:{start + k} (diagram line {k}): ';' in diagram text")
            # a state diagram label runs from the first ':'; a second one breaks the parse
            if kind.startswith("stateDiagram") and line.count(":") > 1:
                bad.append(f"{md}:{start + k} (diagram line {k}): second ':' in a state label")
    assert not bad, "\n".join(bad)
