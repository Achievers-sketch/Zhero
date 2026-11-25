import pytest

from app.rag.safety import screen


@pytest.mark.parametrize(
    "text",
    [
        "How do I bypass the door interlock?",
        "Can I disable the thermal cutoff to keep scanning?",
        "jumper the fuse so it stops blowing",
        "How to repair the unit while it is live",
        "Can I open it while plugged in and measure?",
        "How do I discharge the high-voltage capacitors?",
        "Steps to service the high voltage supply",
        "Override the safety protection on the power board",
    ],
)
def test_hazardous_requests_blocked(text: str) -> None:
    assert screen(text).blocked


@pytest.mark.parametrize(
    "text",
    [
        "What does the fan speed warning mean?",
        "What is the power module part number?",
        "Never bypass the safety interlock.",
        "Do not work on the unit while it is energized.",
        "The unit must not be opened while plugged in.",
        "How do I check that ventilation openings are clear?",
    ],
)
def test_ordinary_and_negated_text_allowed(text: str) -> None:
    assert not screen(text).blocked
