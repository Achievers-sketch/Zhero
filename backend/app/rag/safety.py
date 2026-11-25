"""Deterministic safety screen for hazardous requests and generated text.

Blueprint non-negotiables: never give hazardous repair, safety-interlock bypass or
high-voltage instructions. This is a conservative pattern screen, not a classifier: it
runs on the user's question before any model call and on the generated answer afterwards.
Negated phrasing ("never bypass the interlock") is allowed so documented warnings can be
quoted. Extend the patterns with evidence from the QA set, not by guesswork.
"""

import re
from dataclasses import dataclass

_BYPASS_VERBS = (
    r"(?:bypass|by-pass|defeat|disable|override|jumper|short(?:\s*out)?|circumvent|work\s*around)"
)
_PROTECTIONS = (
    r"(?:interlocks?|safety|thermal\s+(?:cut-?off|fuse|protection)|"
    r"over-?(?:temperature|temp|current|voltage)\s+protection|fuses?|breakers?|"
    r"protective\s+earth|earth(?:ing)?\s+(?:wire|connection|pin)|ground(?:ing)?\s+(?:wire|connection|pin))"
)
_LIVE_STATE = (
    r"(?:live|energi[sz]ed|powered\s+on|plugged\s+in|switched\s+on|"
    r"with\s+(?:the\s+)?(?:power|mains)\s+on)"
)
_INTRUSIVE_VERBS = r"(?:repair|open|service|work\s+on|solder|replace|measure\s+inside|take\s+apart)"
_HV_TERMS = r"(?:high[-\s]?voltage|hv\s+(?:section|supply|board)|mains\s+voltage)"
_HV_VERBS = r"(?:repair|service|replace|work\s+on|open|discharge|measure|test|probe)"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "safety_bypass",
        re.compile(rf"\b{_BYPASS_VERBS}\b[^.?!]{{0,40}}\b{_PROTECTIONS}\b", re.IGNORECASE),
    ),
    (
        "live_work",
        re.compile(
            rf"\b{_INTRUSIVE_VERBS}\b[^.?!]{{0,60}}\b{_LIVE_STATE}\b"
            rf"|\b{_LIVE_STATE}\b[^.?!]{{0,40}}\b{_INTRUSIVE_VERBS}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "high_voltage_work",
        re.compile(
            rf"\b{_HV_VERBS}\b[^.?!]{{0,40}}\b{_HV_TERMS}\b|\b{_HV_TERMS}\b[^.?!]{{0,40}}\b{_HV_VERBS}\b"
            r"|\bdischarge\b[^.?!]{0,30}\bcapacitors?\b",
            re.IGNORECASE,
        ),
    ),
]
_NEGATION_BEFORE = re.compile(
    r"\b(?:not|never|don't|dont|cannot|can't|must\s+not|do\s+not|should\s+not|without)\s+(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)

SAFE_ALTERNATIVE = (
    "I can't help with bypassing safety features or working on live or high-voltage parts. "
    "Please disconnect the equipment from the mains supply, stop using it, and contact "
    "qualified biomedical engineering or manufacturer-authorised service staff. I can still "
    "summarise what the uploaded documents say about safe, user-level checks."
)


@dataclass(frozen=True)
class SafetyResult:
    blocked: bool
    reason: str | None = None


def screen(text: str) -> SafetyResult:
    """Return whether ``text`` asks for (or contains) hazardous instructions."""
    for name, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            preceding = text[max(0, match.start() - 30) : match.start()]
            if _NEGATION_BEFORE.search(preceding):
                continue
            return SafetyResult(True, name)
    return SafetyResult(False)
