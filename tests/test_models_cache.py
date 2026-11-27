"""DEV-01: importing desktop points the model caches into the project (D-028)."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOW = "import desktop, json, os; print(json.dumps([os.environ['HF_HOME'], os.environ['DOCTR_CACHE_DIR']]))"


def _run(env):
    out = subprocess.run([sys.executable, "-c", SHOW], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_dev01_model_caches_inside_project():
    env = {k: v for k, v in os.environ.items() if k not in ("HF_HOME", "DOCTR_CACHE_DIR")}
    hf, doctr = _run(env)
    assert Path(hf) == ROOT / "models" / "huggingface"
    assert Path(doctr) == ROOT / "models" / "doctr"


def test_dev01_preset_cache_kept():
    env = {**os.environ, "HF_HOME": "X:/elsewhere/hf", "DOCTR_CACHE_DIR": "X:/elsewhere/doctr"}
    assert _run(env) == ["X:/elsewhere/hf", "X:/elsewhere/doctr"]
