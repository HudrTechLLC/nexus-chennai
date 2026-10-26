"""Markovian, in-process backend (Python port of the Meterless reference).

Follows engines-ts/markovian/reference/src/{types,configManager,carryover,markers,orchestrator}.ts
(Meterless @1742dec, Apache-2.0):

- config bounds: chunkSize [1000, 128000], maxChunks [1, 32], carryoverTokens [128, 32768],
  overlapTokens [0, 4096]; chunkSize >= framing(400) + carryover + outputBudget(1200);
- token estimator ceil(chars / 4), labelled "estimated";
- carryover cascade in strict order: marker -> LLM compressor -> heuristic key phrases ->
  tail truncation, each level only accepted within the carryover budget;
- savings accounting: standard cost = sum of (prefix + chunk), markovian cost =
  chunks x carryover + total.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Callable

FRAMING_TOKENS = 400
OUTPUT_BUDGET = 1200
BOUNDS = {
    "chunk_size": (1000, 128000),
    "max_chunks": (1, 32),
    "carryover_tokens": (128, 32768),
    "overlap_tokens": (0, 4096),
}


class ConfigValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ChunkConfig:
    chunk_size: int = 8000
    max_chunks: int = 24
    carryover_tokens: int = 800
    overlap_tokens: int = 0

    @property
    def input_budget(self) -> int:
        """Tokens left for records in one chunk after framing, carryover and output."""
        return self.chunk_size - FRAMING_TOKENS - self.carryover_tokens - OUTPUT_BUDGET

    def as_dict(self) -> dict:
        return asdict(self)


def resolve_config(**overrides: int) -> ChunkConfig:
    cfg = ChunkConfig(**overrides)
    for key, (lo, hi) in BOUNDS.items():
        v = getattr(cfg, key)
        if not isinstance(v, int) or isinstance(v, bool):
            raise ConfigValidationError(f"{key} must be an integer")
        if v < lo or v > hi:
            raise ConfigValidationError(f"{key}={v} outside [{lo}, {hi}]")
    if cfg.chunk_size < FRAMING_TOKENS + cfg.carryover_tokens + OUTPUT_BUDGET:
        raise ConfigValidationError(
            f"chunk_size={cfg.chunk_size} < framing({FRAMING_TOKENS}) + carryover({cfg.carryover_tokens})"
            f" + outputBudget({OUTPUT_BUDGET})")
    return cfg


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


# ------------------------------------------------------------------ markers

_STATE_TAIL = re.compile(r"\[STATE_CHECKPOINT\]\s*([\s\S]*)$")
_FINAL = re.compile(r"\[TASK_COMPLETE\]")


def parse_markers(raw: str) -> tuple[str | None, bool, str]:
    """(state, done, cleaned) for the canonical square-bracket markers."""
    m = _STATE_TAIL.search(raw)
    state = m.group(1).strip() if m else None
    done = bool(_FINAL.search(raw))
    cleaned = _STATE_TAIL.sub("", raw)
    cleaned = _FINAL.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+$", "", cleaned, flags=re.M)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return state, done, cleaned


# ---------------------------------------------------------------- carryover

_KEY_PHRASE = re.compile(
    r"(?:^|\n|\.\s+)((?:Therefore|Key insight|Status|Decision|Decided|Next|Remaining|Completed)[^.\n]*)", re.I)


def next_carryover(marker_state: str | None, previous: str, chunk_text: str, budget: int,
                   compressor: Callable[[str], str] | None = None) -> tuple[str, str]:
    """(carryover, level). The result never exceeds `budget` estimated tokens."""
    if marker_state is not None:
        sanitized = re.sub(r"[<>\[\]@-]{3,}", "", marker_state).strip()
        if len(sanitized) >= 24 and estimate_tokens(sanitized) <= budget:
            return sanitized, "marker"
    if compressor is not None:
        try:
            prompt = (f"Previous state:\n{previous or '(none)'}\n\nLatest chunk (tail):\n{chunk_text[-2000:]}\n\n"
                      "Compress into 3-5 critical points as a labeled block:\n"
                      "COMPLETED: ...\nREMAINING: ...\nDECISIONS: ...\nCONTEXT: ...")
            compressed = compressor(prompt).strip()
            if len(compressed) >= 24 and estimate_tokens(compressed) <= budget:
                return compressed, "llm"
        except Exception:  # noqa: BLE001 - the cascade falls through by design
            pass
    phrases = [m.group(1).strip() for m in _KEY_PHRASE.finditer(chunk_text)][:5]
    if phrases:
        summary = "; ".join(phrases)
        if estimate_tokens(summary) <= budget:
            return summary, "heuristic"
    words = (chunk_text or previous).split()
    tail = ""
    for word in reversed(words):
        candidate = word + (" " + tail if tail else "")
        if estimate_tokens(candidate) > budget:
            break
        tail = candidate
    return tail, "truncation"


def run_efficiency(chunk_tokens: list[int], cfg: ChunkConfig) -> dict:
    total = sum(chunk_tokens)
    standard, prefix = 0, 0
    for t in chunk_tokens:
        standard += prefix + t
        prefix += t
    markovian = len(chunk_tokens) * cfg.carryover_tokens + total
    saved = max(0, standard - markovian)
    return {"totalTokensUsed": total, "standardCost": standard, "markovianCost": markovian,
            "tokensSaved": saved, "efficiencyPercent": (saved / standard * 100) if standard else 0.0}
