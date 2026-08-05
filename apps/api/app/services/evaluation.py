"""Evaluation harness: sensitivity/specificity vs gold-labeled set.

Primary KPI for PV literature monitoring: sensitivity (missed-case rate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.ai.scorer import score_article
from app.services.triage.engine import route_screening
from app.models.entities import QueueType

# Gold set lives in monorepo data/seed
_GOLD_PATHS = [
    Path(__file__).resolve().parents[4] / "data" / "seed" / "gold_labels.json",
    Path(__file__).resolve().parents[3] / "data" / "seed" / "gold_labels.json",
]


def load_gold_set(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the validation set, or return empty if none is configured.

    No gold set ships with the application. A sensitivity figure computed on
    invented articles would be a fabricated KPI, so the evaluation reports
    "not configured" until a real, labelled set is supplied.
    """
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for p in _GOLD_PATHS:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return []


def is_surfaced(queue: QueueType) -> bool:
    """Article is considered 'surfaced to human' if not pure auto-clear."""
    return queue != QueueType.AUTO_CLEAR


async def evaluate_gold_set(
    gold: list[dict[str, Any]] | None = None,
    product_names: list[str] | None = None,
) -> dict[str, Any]:
    gold = gold if gold is not None else load_gold_set()
    if not gold:
        return {
            "configured": False,
            "message": (
                "No validation set is configured. Supply a labelled gold set at "
                "data/seed/gold_labels.json to measure screening sensitivity."
            ),
            "total": 0,
        }
    if not product_names:
        raise ValueError(
            "product_names is required — evaluation must run against the "
            "products actually being monitored."
        )

    tp = fp = tn = fn = 0
    details: list[dict[str, Any]] = []

    for item in gold:
        out, model_id, is_mock, _meta = await score_article(
            title=item["title"],
            abstract=item.get("abstract"),
            product_names=product_names,
            mesh_terms=item.get("mesh_terms") or [],
        )
        decision = route_screening(out)
        gold_icsr = bool(item.get("is_icsr") or item.get("label") == "icsr")
        surfaced = is_surfaced(decision.queue) or decision.hard_rule_triggered

        # For evaluation: gold "should_surface" overrides pure ICSR if provided
        should_surface = item.get("should_surface")
        if should_surface is None:
            should_surface = gold_icsr

        if should_surface and surfaced:
            tp += 1
            outcome = "tp"
        elif should_surface and not surfaced:
            fn += 1
            outcome = "fn"
        elif not should_surface and surfaced:
            fp += 1
            outcome = "fp"
        else:
            tn += 1
            outcome = "tn"

        details.append(
            {
                "id": item.get("id") or item.get("pmid"),
                "title": item["title"][:120],
                "gold_should_surface": should_surface,
                "gold_is_icsr": gold_icsr,
                "system_queue": decision.queue.value,
                "system_composite": out.composite,
                "hard_rules": decision.hard_rules,
                "outcome": outcome,
                "model_id": model_id,
                "is_mock": is_mock,
            }
        )

    n = tp + fp + tn + fn
    sensitivity = tp / (tp + fn) if (tp + fn) else None  # recall for cases
    specificity = tn / (tn + fp) if (tn + fp) else None
    precision = tp / (tp + fp) if (tp + fp) else None
    f1 = (
        2 * precision * sensitivity / (precision + sensitivity)
        if precision is not None and sensitivity is not None and (precision + sensitivity)
        else None
    )

    return {
        "n": n,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "sensitivity": round(sensitivity, 4) if sensitivity is not None else None,
        "specificity": round(specificity, 4) if specificity is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "primary_kpi": "sensitivity",
        "missed_cases": [d for d in details if d["outcome"] == "fn"],
        "details": details,
    }
