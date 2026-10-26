"""Unit tests for demo/narrate.py (narration blocks for the demo video). No network."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("narrate", ROOT / "demo" / "narrate.py")
narrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(narrate)

SAMPLE = """# Video
## ElevenLabs narration text (one block per segment)

Intro text.

```
[seg_01]
First block, line one.
Line two.

[seg_02]
Second block.
```
"""


def test_parses_blocks_in_order_and_joins_lines():
    blocks = narrate.parse_blocks(SAMPLE)
    assert list(blocks) == ["seg_01", "seg_02"]
    assert blocks["seg_01"] == "First block, line one. Line two."


def test_rejects_missing_heading_and_empty_block():
    with pytest.raises(ValueError):
        narrate.parse_blocks("no narration here")
    with pytest.raises(ValueError):
        narrate.parse_blocks(SAMPLE.replace("Second block.", ""))


def test_the_real_script_has_nine_blocks():
    blocks = narrate.parse_blocks((ROOT / "engg/docs/submission/VIDEO_SCRIPT.md").read_text(encoding="utf-8"))
    assert list(blocks) == [f"seg_{i:02d}" for i in range(1, 10)]


def test_timings():
    assert narrate.spoken_seconds("a " * 24) == 10.0
    assert narrate.mp3_seconds(16000) == 1.0  # 128 kbps


def test_key_comes_from_a_file_or_one_command_env_never_the_command_line(tmp_path, monkeypatch):
    f = tmp_path / "k"
    f.write_text("abc\r\n", encoding="utf-8")
    assert narrate.read_key(str(f)) == "abc"
    monkeypatch.setenv("XI_API_KEY", "envkey")
    assert narrate.read_key(None) == "envkey"
    monkeypatch.delenv("XI_API_KEY")
    with pytest.raises(SystemExit):
        narrate.read_key(None)
    src = (ROOT / "demo" / "narrate.py").read_text(encoding="utf-8")
    assert "--api-key" not in src  # no flag that would put the key in shell history
