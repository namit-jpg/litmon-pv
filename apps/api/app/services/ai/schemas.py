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

    @property
    def composite(self) -> float:
        # Default weights — versioned in config; logged on ScreeningResult
        return round(
            0.35 * self.product_match
            + 0.30 * self.event_relevance
            + 0.35 * self.icsr_criteria_match,
            4,
        )
