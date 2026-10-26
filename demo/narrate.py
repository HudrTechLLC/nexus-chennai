"""Turn the video narration blocks into MP3s with the ElevenLabs API (WS5-07).

The blocks live in engg/docs/submission/VIDEO_SCRIPT.md, under "ElevenLabs narration text", as
``[seg_NN]`` followed by the text. Each block becomes demo/out/seg_NN.mp3 (out/ is gitignored).
Settings follow the script: one voice, stability 0.5, similarity 0.75.

ElevenLabs is used only for the demo video's voice-over. It is not part of the running product.

The API key is read from a file, never from the command line, and never printed:

    python demo/narrate.py --key-file ~/.secrets/elevenlabs.key --list-voices
    python demo/narrate.py --key-file ~/.secrets/elevenlabs.key --voice <voice_id>
    python demo/narrate.py --key-file ~/.secrets/elevenlabs.key --voice <voice_id> --only seg_03 seg_07
    python demo/narrate.py --dry-run          # parse the blocks and print timings; no key, no network

XI_API_KEY in the environment also works (set it for one command only; never export it).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "engg" / "docs" / "submission" / "VIDEO_SCRIPT.md"
OUT = Path(__file__).resolve().parent / "out"
API = "https://api.elevenlabs.io/v1"
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.5, "similarity_boost": 0.75}
WORDS_PER_SECOND = 2.4  # the pace VIDEO_SCRIPT is written for
SECTION = "## ElevenLabs narration text"


# =====================
# Parsing
# =====================

def parse_blocks(markdown: str) -> dict[str, str]:
    """{"seg_01": text, ...} from the first fenced block after the narration heading."""
    start = markdown.find(SECTION)
    if start < 0:
        raise ValueError(f"heading {SECTION!r} not found")
    fence = re.search(r"```[^\n]*\n(.*?)\n```", markdown[start:], re.S)
    if not fence:
        raise ValueError("no fenced block after the narration heading")
    blocks: dict[str, str] = {}
    current: str | None = None
    for line in fence.group(1).splitlines():
        m = re.fullmatch(r"\[(seg_\d{2})\]\s*", line)
        if m:
            current = m.group(1)
            if current in blocks:
                raise ValueError(f"duplicate block {current}")
            blocks[current] = ""
        elif current is not None and line.strip():
            blocks[current] = (blocks[current] + " " + line.strip()).strip()
    empty = [k for k, v in blocks.items() if not v]
    if not blocks or empty:
        raise ValueError(f"no text for {empty or 'any block'}")
    return blocks


def words(text: str) -> int:
    return len(text.split())


def spoken_seconds(text: str) -> float:
    return round(words(text) / WORDS_PER_SECOND, 1)


def mp3_seconds(n_bytes: int, kbps: int = 128) -> float:
    """Duration of a constant-bitrate MP3 (ElevenLabs mp3_44100_128)."""
    return round(n_bytes * 8 / (kbps * 1000), 1)


# =====================
# API
# =====================

def read_key(key_file: str | None) -> str:
    if key_file:
        key = Path(os.path.expanduser(key_file)).read_text(encoding="utf-8").strip()
    else:
        key = os.environ.get("XI_API_KEY", "").strip()
    if not key:
        raise SystemExit("no API key: pass --key-file <path> (preferred) or set XI_API_KEY for this one command")
    return key


def _request(url: str, key: str, body: dict | None = None) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"xi-api-key": key, "Content-Type": "application/json",
                                          "Accept": "audio/mpeg" if body is not None else "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:  # the error body never contains the key
        raise SystemExit(f"ElevenLabs HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None


def list_voices(key: str) -> None:
    voices = json.loads(_request(f"{API}/voices", key)).get("voices", [])
    for v in voices:
        labels = v.get("labels") or {}
        print(f"{v.get('voice_id')}  {v.get('name')}  accent={labels.get('accent', '-')}  gender={labels.get('gender', '-')}")


def synthesise(key: str, voice: str, text: str) -> bytes:
    return _request(f"{API}/text-to-speech/{voice}?output_format=mp3_44100_128", key,
                    {"text": text, "model_id": MODEL, "voice_settings": SETTINGS})


# =====================
# Main
# =====================

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key-file", help="path to a file holding the ElevenLabs API key")
    ap.add_argument("--voice", help="ElevenLabs voice id (see --list-voices)")
    ap.add_argument("--only", nargs="*", help="segment ids to (re)generate, e.g. seg_03")
    ap.add_argument("--list-voices", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="parse and print timings only")
    args = ap.parse_args(argv)

    blocks = parse_blocks(SCRIPT.read_text(encoding="utf-8"))
    if args.only:
        missing = sorted(set(args.only) - set(blocks))
        if missing:
            raise SystemExit(f"unknown segments: {missing}")
        blocks = {k: v for k, v in blocks.items() if k in args.only}

    if args.dry_run:
        total = 0.0
        for seg, text in blocks.items():
            total += spoken_seconds(text)
            print(f"{seg}: {words(text)} words, ~{spoken_seconds(text)} s at {WORDS_PER_SECOND} w/s")
        print(f"total ~{round(total, 1)} s")
        return 0

    key = read_key(args.key_file)
    if args.list_voices:
        list_voices(key)
        return 0
    if not args.voice:
        raise SystemExit("--voice is required (see --list-voices)")

    OUT.mkdir(exist_ok=True)
    total = 0.0
    for seg, text in blocks.items():
        audio = synthesise(key, args.voice, text)
        path = OUT / f"{seg}.mp3"
        path.write_bytes(audio)
        secs = mp3_seconds(len(audio))
        total += secs
        print(f"{seg}: {words(text)} words -> {path.relative_to(ROOT)} ~{secs} s (script estimate {spoken_seconds(text)} s)")
    print(f"total ~{round(total, 1)} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
