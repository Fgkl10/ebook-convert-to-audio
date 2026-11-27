"""Package layering (D-033): core <- ocr, tts <- server; nothing imports server. IDs: LAY-xx in desktop/docs/test-cases.md.

Imports are read from the source (ast), so a rule holds even for code paths the other tests never run.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

from desktop import PROJECT

DESKTOP = PROJECT / "desktop"
PACKAGES = ("core", "ocr", "tts", "server")
# What each package may import from the others (besides itself and the `desktop` root, which only sets paths).
ALLOWED = {"core": set(), "ocr": {"core"}, "tts": {"core"}, "server": {"core", "ocr", "tts"}}
# The one deliberate exception: normalize() imports OCR inside the function, only for a PDF.
LAZY_ALLOWED = {("core/normalize.py", "ocr")}
NO_WEB = ("fastapi", "starlette", "uvicorn", "pydantic", "zeroconf", "qrcode")
NO_GPU_TOP_LEVEL = ("torch", "kokoro", "doctr", "misaki")


def _imports(path: Path):
    """(absolute module, at module level?) for every import in a file under desktop/."""
    pkg = path.relative_to(PROJECT).with_suffix("").parts[:-1]  # e.g. ('desktop', 'core')
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top = {id(n) for n in tree.body}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, id(node) in top
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = ".".join(pkg[:len(pkg) - node.level + 1])
                mod = f"{base}.{node.module}" if node.module else base
                if not node.module:  # "from . import service" names modules
                    for alias in node.names:
                        yield f"{mod}.{alias.name}", id(node) in top
                    continue
            else:
                mod = node.module
            yield mod, id(node) in top


def _package_of(module: str):
    m = re.match(r"desktop\.(\w+)", module)
    return m.group(1) if m and m.group(1) in PACKAGES + ("web",) else None


def _files(package):
    return sorted((DESKTOP / package).rglob("*.py"))


def test_lay01_dependencies_go_one_way():
    problems = []
    for package in PACKAGES:
        for f in _files(package):
            rel = f.relative_to(DESKTOP).as_posix()
            for module, at_top in _imports(f):
                target = _package_of(module)
                if target is None or target == package:
                    continue
                if target in ALLOWED[package]:
                    continue
                if not at_top and (rel, target) in LAZY_ALLOWED:
                    continue
                problems.append(f"{rel} imports {module}")
    assert problems == []


def test_lay02_nothing_imports_server_or_web():
    for package in ("core", "ocr", "tts"):
        for f in _files(package):
            for module, _ in _imports(f):
                assert _package_of(module) not in ("server", "web"), f"{f.name} imports {module}"
    assert not list((DESKTOP / "web").rglob("*.py"))  # the frontend is static files only


def test_lay03_no_web_code_outside_server_and_no_gpu_imports_at_load():
    for package in ("core", "ocr", "tts"):
        for f in _files(package):
            for module, at_top in _imports(f):
                root = module.split(".")[0]
                assert root not in NO_WEB, f"{f.relative_to(DESKTOP)} imports {module}"
                if package == "core":
                    assert root not in NO_GPU_TOP_LEVEL, f"core imports {module}"
                elif at_top:  # ocr/tts load torch, Kokoro and docTR only when they run
                    assert root not in NO_GPU_TOP_LEVEL, f"{f.relative_to(DESKTOP)} imports {module} at load"


def test_lay04_cleaning_without_ocr_never_loads_it():
    """Optional OCR: importing core and cleaning a TXT loads neither desktop.ocr nor the web stack."""
    code = ("import sys, tempfile, pathlib; from desktop.core.normalize import normalize; "
            "d = pathlib.Path(tempfile.mkdtemp()); p = d / 'a.txt'; "
            "p.write_text('Chapter 1\\n\\n' + 'The cat sat on the mat and it was happy. ' * 40); "
            "normalize(p, ignore_language=True); "
            "print(sorted(m for m in sys.modules if m.startswith(('desktop.ocr', 'desktop.server', 'desktop.tts', "
            "'fastapi', 'torch', 'doctr'))))")
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]", out.stdout + out.stderr


def test_lay05_installed_commands_point_at_mains():
    text = (PROJECT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = dict(re.findall(r'^(ebook-[\w-]+)\s*=\s*"([\w.:]+)"', text, re.M))
    assert set(scripts) == {"ebook-server", "ebook-normalize", "ebook-convert"}
    for target in scripts.values():
        module, func = target.split(":")
        out = subprocess.run([sys.executable, "-c", f"import {module} as m; assert callable(m.{func})"],
                             cwd=PROJECT, capture_output=True, text=True)
        assert out.returncode == 0, target + out.stderr
