from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CriterionCheck(BaseModel):
    present: bool = False
    evidence: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class IcsrPrecheck(BaseModel):
    identifiable_patient: CriterionCheck = Field(default_factory=CriterionCheck)
    suspect_drug: CriterionCheck = Field(default_factory=CriterionCheck)
    adverse_event: CriterionCheck = Field(default_factory=CriterionCheck)
    identifiable_reporter: CriterionCheck = Field(default_factory=CriterionCheck)


class ReasonTag(BaseModel):
    code: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class ScreeningOutput(BaseModel):
    product_match: float = Field(ge=0.0, le=1.0)
    event_relevance: float = Field(ge=0.0, le=1.0)
    icsr_criteria_match: float = Field(ge=0.0, le=1.0)
    entities: dict[str, Any] = Field(default_factory=dict)
    icsr_precheck: IcsrPrecheck = Field(default_factory=IcsrPrecheck)
    reason_tags: list[ReasonTag] = Field(default_factory=list)
    hard_rule_candidates: list[
        Literal[
            "death_with_product",
            "pediatric",
            "pregnancy",
            "ime",
            "ambiguous_icsr",
        ]
    ] = Field(default_factory=list)
    summary_for_reviewer: str = ""
    # Step-5 extraction fields. These are deliberately separate from the raw
    # entities bag so they can be rendered consistently and validated by the
    # regulatory workflow. Every value must be grounded in the supplied
    # title/abstract; null is preferable to invention.
    indication: str | None = None
    dosage: str | None = None
    outcome: str | None = None
    seriousness: str | None = None
    country_of_occurrence: str | None = None
    reporter_type: str | None = None
    concomitant_medication: str | None = None
    article_excerpts: list[str] = Field(default_factory=list)
    relevance_reason: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def composite(self) -> float:
        # Default weights — versioned in config; logged on ScreeningResult
        return round(
            0.35 * self.product_match
            + 0.30 * self.event_relevance
            + 0.35 * self.icsr_criteria_match,
            4,
        )
