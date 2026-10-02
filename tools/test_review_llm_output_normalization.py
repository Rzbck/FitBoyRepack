#!/usr/bin/env python3
from __future__ import annotations

import review_llm_autodrain as worker


def main() -> None:
    qid, confidence, reason = worker.validate_decision(
        {
            "candidate": "I choose Q100 (Example Game)",
            "confidence_score": "97%",
            "rationale": "same game",
        },
        {"Q100", "Q200"},
    )
    assert qid == "Q100"
    assert confidence == 0.97
    assert reason == "same game"

    qid2, confidence2, _ = worker.validate_decision(
        {"candidate_id": "null", "confidence": "0.40", "reason": "uncertain"},
        {"Q100"},
    )
    assert qid2 is None
    assert confidence2 == 0.40

    try:
        worker.validate_decision(
            {"candidate_id": "Q999", "confidence": 0.99, "reason": "unsupported"},
            {"Q100"},
        )
    except ValueError as exc:
        assert "outside the supplied evidence" in str(exc)
    else:
        raise AssertionError("unsupported candidate must be rejected")

    system, _ = worker.build_decision_prompt(
        {"title": "Example Game Deluxe", "genres": ["Adventure"]},
        [{
            "id": "Q100",
            "label": "Example Game",
            "description": "video game",
            "release_dates": ["2024-05-01"],
            "genres": ["Adventure game"],
            "developers": [],
            "publishers": [],
            "platforms": ["Microsoft Windows"],
            "url": "https://www.wikidata.org/wiki/Q100",
        }],
    )
    assert system.startswith("/no_think")

    print("review llm output normalization OK")


if __name__ == "__main__":
    main()
