"""Scout Intent, implemented against the Meterless Scout spec (no runnable reference exists).

Spec source: Meterless engines/scout-intent/docs/{architecture,intent-registry,risk-and-policy,
eval-harness}.md @1742dec (Apache-2.0). Implemented here:

- an intent registry for Nexus (spec E4): analyst query intents and public tip intents;
- the guard stack, each layer returning pass/warn/block with evidence:
  injection (pattern, embedded control, role drift, tool reference), threat, abuse, spam,
  emergency, PII (flagged and redacted, never logged in full);
- reduction to one action: any block -> quarantine; emergency -> urgent; else clean.
  Blocks are sparse by design ("warn loudly, block sparingly"): only injection, threat,
  abuse and spam block.

Scoring is deterministic: weighted regex/keyword hits per intent, highest score wins,
ties broken by registry order. Below the reject band (score < 1) a query falls back to
`entity_lookup` with a clarification flag; a tip falls back to `useful_info`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ----------------------------------------------------------------- registry

QUERY_ROUTES = {
    "case_lookup": "case",
    "entity_lookup": "entity",
    "similar_mo": "similar_mo",
    "map_filter": "map",
    "image_search": "image",
    "series_question": "series",
    "stats_question": "stats",
}
TIP_ROUTES = {
    "useful_info": "tip_intake",
    "media_only": "tip_intake",
    "spam": "quarantine",
    "abuse": "quarantine",
    "threat": "quarantine",
    "prompt_injection": "quarantine",
    "emergency": "emergency",
}
QUERY_INTENTS = tuple(QUERY_ROUTES)
TIP_INTENTS = tuple(TIP_ROUTES)


def _rx(*patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(p, re.I) for p in patterns]


# Patterns are language-generic; place names and local terms come from the data, not code (D-004).
FIR_NO = r"\b\d{1,5}\s*/\s*(?:19|20)\d{2}\b"
PLATE = r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{0,3}[\s-]?\d{3,4}\b"
PHONE = r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\d{10}(?!\d)"
EMAIL = r"[\w.+-]+@[\w-]+\.[\w.-]+"

QUERY_SIGNALS: dict[str, list[tuple[re.Pattern[str], float]]] = {
    "case_lookup": [(p, w) for p, w in zip(_rx(FIR_NO, r"\b(fir|case|crime)\s*(no\.?|number|#)\b",
                                                r"\b(open|show|pull up|details of)\b.*\b(fir|case)\b"),
                                            (3.0, 2.0, 1.5))],
    "entity_lookup": [(p, w) for p, w in zip(_rx(PLATE, PHONE, r"\bwho is\b", r"\b(alias|accused|suspect|offender)\b",
                                                  r"\b(history ?sheet(er)?|known as|a\.k\.a)\b",
                                                  r"\b(vehicle|plate|number plate|registration)\b"),
                                              (3.0, 2.5, 2.0, 1.2, 1.5, 1.0))],
    "similar_mo": [(p, w) for p, w in zip(_rx(r"\bsimilar\b", r"\b(same|matching|like this)\s+(mo|modus|method|pattern)\b",
                                               r"\b(mo|modus operandi|method of entry|entry method)\b",
                                               r"\b(crimes?|cases|thefts?|burglar(y|ies)|robber(y|ies)|snatch(ing|ings)|"
                                               r"break-ins?)\s+(like|where|with|in which|involving)\b",
                                               r"\b(m\.o\.)", r"\bsimilar (to|pattern|cases|crimes)\b"),
                                           (1.5, 3.0, 1.5, 2.5, 1.5, 2.0))],
    "map_filter": [(p, w) for p, w in zip(_rx(r"\b(on|in) (the )?map\b", r"\bnear(by)?\b|\bwithin \d+\s*(m|km)\b",
                                               r"\b(hotspots?|heat ?map|around)\b", r"\b(show|plot|filter)\b.*\b(in|near|around)\b",
                                               r"\b(last|past) (night|week|month|\d+ days)\b"),
                                           (3.0, 2.0, 2.0, 1.0, 0.8))],
    "image_search": [(p, w) for p, w in zip(_rx(r"\b(photos?|images?|pictures?|cctv stills?|stills?|screenshots?|face|frames?)\b",
                                                 r"\blooks? like (this|the)\b", r"\b(match|find).*(photo|image|face)\b"),
                                             (2.5, 2.0, 1.5))],
    "series_question": [(p, w) for p, w in zip(_rx(r"\bseries\b", r"\b(linked|connected) (crimes|cases)\b",
                                                    r"\bsame (gang|offenders?|crew)\b", r"\bdossier\b"),
                                                (3.0, 2.0, 2.0, 2.0))],
    "stats_question": [(p, w) for p, w in zip(_rx(r"\bhow many\b", r"\b(count|number of|total|trend|rate|percentage|average)\b",
                                                   r"\b(compare|comparison|vs\.?|versus)\b", r"\b(per|by) (station|month|week|ward)\b"),
                                               (3.0, 1.5, 1.0, 1.5))],
}

INJECTION = _rx(
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(previous|prior|above|earlier|all|your|the)\b.{0,30}"
    r"\b(instructions?|rules?|prompts?|guidelines|directives|polic(y|ies)|context)\b",
    r"\b(system|developer|hidden|initial)\s+(prompt|message|instructions?)\b",
    r"</?\s*(system|assistant|user|instructions?|tool|im_start|im_end)\s*>",
    r"\[/?(INST|SYS|SYSTEM)\]|<<\s*SYS\s*>>|<\|(im_start|im_end|system|endoftext)\|>",
    r"\byou are (now|no longer)\b|\bfrom now on,? you\b|\bact as (an?|the)\b|\bpretend (to be|you are)\b",
    r"\b(jailbreak|DAN mode|developer mode|god mode)\b",
    r"\b(new|updated) (instructions?|rules)\s*:",
    r"\b(call|invoke|run|execute|use) (the )?(tool|function|api|endpoint|command)\b",
    r"\b(mark|set|flag|classify) (this|the|my) (tip|report|message) (as )?(verified|urgent|trusted|clean|safe)\b",
    r"\b(delete|drop|truncate|update)\s+(table|from|all|the database|records)\b|;\s*--|\bunion\s+select\b",
    r"\b(reveal|print|show|output|repeat)\b.{0,20}\b(your|the) (prompt|instructions|system|api key|token|password)s?\b",
    r"\bassistant\s*:\s|\bsystem\s*:\s",
    r"(?:[A-Za-z0-9+/]{40,}={0,2})",
)
THREAT = _rx(
    r"\b(i|we)('ll| will|'m going to| am going to|'re going to| are going to| gonna)\s+"
    r"(kill|shoot|stab|bomb|burn|hurt|attack|finish|beat)\b",
    r"\b(will|gonna|going to) (die|be killed|be hurt)\b",
    r"\b(bomb|explosive|ied)\b.{0,40}\b(plant|placed|set|will|going)\b",
    r"\byou('ll| will) (die|pay|regret)\b|\bwatch your back\b|\b(dead|death) (man|threat)\b",
    r"\b(kill|murder|shoot)\s+(the |that |this )?(inspector|officer|constable|police|you|him|her|them)\b",
)
ABUSE = _rx(
    r"\b(idiot|stupid|useless|corrupt|bastard|moron|scum|pigs?)\b.{0,30}\b(police|cops?|officers?|inspector|you|department)\b",
    r"\b(police|cops?|officers?|inspector|department)\b.{0,30}\b(idiots?|stupid|useless|bastards?|morons?|scum|pigs?)\b",
    r"\b(f+u+c+k+|sh[i1]t|b[i1]tch|a+s+s+h+o+l+e+)\b",
)
SPAM = _rx(
    r"https?://|www\.\S+|\bbit\.ly\b",
    r"\b(buy now|click here|free (gift|money|recharge)|lottery|you have won|limited offer|earn \S+ (per|a) day|"
    r"crypto|bitcoin|loan approved|work from home|subscribe|follow me|promo code|discount)\b",
    r"(.)\1{7,}",
)
EMERGENCY = _rx(
    r"\b(happening|going on|in progress)\s+(right )?now\b|\bright now\b",
    r"\b(help|save) (me|us)\b|\bsomeone (is )?(bleeding|dying|unconscious|injured)\b",
    r"\b(bleeding|on fire|fire|being attacked|being beaten|kidnapp(ed|ing)|abduct(ed|ing)|gun|knife)\b",
    r"\b(collapsed|unconscious|not breathing|heart attack|trapped|drowning|overdose)\b",
    r"\b(he|she|they)('s| is| are) (still )?(here|inside|outside|following me|breaking in)\b",
)
PII = {"phone": re.compile(PHONE), "email": re.compile(EMAIL)}


@dataclass
class Layer:
    name: str
    verdict: str  # pass | warn | block
    evidence: list[str] = field(default_factory=list)


def _hits(patterns: list[re.Pattern[str]], text: str) -> list[str]:
    out = []
    for p in patterns:
        m = p.search(text)
        if m:
            out.append(m.group(0)[:40])
    return out


def guard(text: str, kind: str) -> list[Layer]:
    """Run every guard layer. Queries skip the tip-only layers (spam/abuse/emergency)."""
    layers = [Layer("injection", "block" if (ev := _hits(INJECTION, text)) else "pass", ev)]
    if kind == "tip":
        layers.append(Layer("threat", "block" if (ev := _hits(THREAT, text)) else "pass", ev))
        layers.append(Layer("abuse", "block" if (ev := _hits(ABUSE, text)) else "pass", ev))
        layers.append(Layer("spam", "block" if (ev := _hits(SPAM, text)) else "pass", ev))
        layers.append(Layer("emergency", "warn" if (ev := _hits(EMERGENCY, text)) else "pass", ev))
        pii = [k for k, p in PII.items() if p.search(text)]
        layers.append(Layer("pii", "warn" if pii else "pass", pii))
    return layers


def redact(text: str) -> str:
    for kind, p in PII.items():
        text = p.sub(f"[{kind} redacted]", text)
    return text


def score_query(text: str) -> list[tuple[str, float]]:
    scores = []
    for intent, signals in QUERY_SIGNALS.items():
        s = sum(w for p, w in signals if p.search(text))
        scores.append((intent, s))
    order = {k: i for i, k in enumerate(QUERY_INTENTS)}
    return sorted(scores, key=lambda t: (-t[1], order[t[0]]))


def classify(text: str, kind: str) -> dict:
    kind = (kind or "query").lower()
    if kind not in ("query", "tip"):
        raise ValueError("kind must be 'query' or 'tip'")
    text = text or ""
    layers = guard(text, kind)
    by = {layer.name: layer for layer in layers}
    risk = [f"{layer.name}:{layer.verdict}" for layer in layers if layer.verdict != "pass"]

    if kind == "query":
        if by["injection"].verdict == "block":
            return {"route": "quarantine", "intent": "prompt_injection", "risk": risk, "action": "quarantine",
                    "scores": {}, "clarify": False, "evidence": {"injection": len(by["injection"].evidence)}}
        ranked = score_query(text)
        intent, top = ranked[0]
        clarify = top < 1.0
        if clarify:
            intent = "entity_lookup"
        return {"route": QUERY_ROUTES[intent], "intent": intent, "risk": risk, "action": "clean",
                "scores": {k: round(v, 2) for k, v in ranked[:3]}, "clarify": clarify, "evidence": {}}

    # tips: block order = injection, threat, abuse, spam
    for name, intent in (("injection", "prompt_injection"), ("threat", "threat"), ("abuse", "abuse"), ("spam", "spam")):
        if by[name].verdict == "block":
            return {"route": TIP_ROUTES[intent], "intent": intent, "risk": risk, "action": "quarantine",
                    "emergency": by["emergency"].verdict == "warn", "redacted_text": None,
                    "evidence": {name: len(by[name].evidence)}}
    if by["emergency"].verdict == "warn":
        return {"route": TIP_ROUTES["emergency"], "intent": "emergency", "risk": risk, "action": "urgent",
                "emergency": True, "redacted_text": redact(text), "evidence": {}}
    intent = "media_only" if not text.strip() or len(re.findall(r"[A-Za-z]{2,}", text)) < 3 else "useful_info"
    return {"route": TIP_ROUTES[intent], "intent": intent, "risk": risk, "action": "clean", "emergency": False,
            "redacted_text": redact(text), "evidence": {}}
