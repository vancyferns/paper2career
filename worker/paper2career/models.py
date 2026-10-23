from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OcrLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Advertisement:
    """One printed classified advertisement (may contain several vacancies)."""
    text: str
    lines: list[OcrLine]
    section: str | None           # e.g. "SITUATIONS VACANT", or None when unknown
    column: int
    bbox: tuple[float, float, float, float]
    ocr_confidence: float
    ad_reference: str | None = None
    terminated: bool = True       # False when a reference-numbered page has text that never reached a number


@dataclass
class JobDraft:
    """Structured fields extracted from an advertisement. Unknown fields stay None."""
    title: str
    employer: str | None = None
    description: str = ""
    location: str | None = None
    qualification: str | None = None
    experience: str | None = None
    salary_text: str | None = None
    contact_phones: list[str] = field(default_factory=list)
    contact_emails: list[str] = field(default_factory=list)
    application_instructions: str | None = None
    deadline: str | None = None           # ISO date, only when printed in the ad
    confidence: float = 0.0
    uncertain_fields: list[str] = field(default_factory=list)
    role_index: int = 0                   # position of this role inside a multi-role ad
