"""The Mermaid diagrams in the docs avoid what breaks GitHub's renderer (DOC-01)."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# not walked: tools, build output and data folders (models/ alone holds thousands of files)
SKIP = {".venv", ".scratch", "node_modules", "build", ".git", ".gradle", "models", "cache", "library", "drafts",
        "samples"}
ENTITY = re.compile(r"&#?\w+;")  # &lt; &amp; &#35; keep their semicolon


def markdown_files():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        yield from (Path(folder) / f for f in sorted(files) if f.endswith(".md"))


def mermaid_blocks():
    for md in markdown_files():
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
