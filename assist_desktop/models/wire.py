"""Wire types. Mirrors v4's assist/types.py across the HTTP boundary.

Names match the server's deliberately, so a grep for `SafetyBlock` finds both
ends. `from_dict` ignores unknown keys: a newer service must be able to add a
field without breaking an older client.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SafetyBlock:
    level: str
    text: str
    source_chunk_id: Optional[int] = None
    page: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SafetyBlock":
        return cls(level=d.get("level", ""), text=d.get("text", ""),
                   source_chunk_id=d.get("source_chunk_id"), page=d.get("page"))


@dataclass(frozen=True)
class Citation:
    page: int
    procedure_name: str = ""
    chunk_id: Optional[int] = None
    method: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Citation":
        return cls(page=d.get("page", 0),
                   procedure_name=d.get("procedure_name", ""),
                   chunk_id=d.get("chunk_id"), method=d.get("method", ""))


@dataclass(frozen=True)
class Image:
    id_code: str = ""
    image_path: str = ""
    caption: str = ""
    step_num: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Image":
        return cls(id_code=d.get("id_code", ""),
                   image_path=d.get("image_path", ""),
                   caption=d.get("caption", ""), step_num=d.get("step_num"))


@dataclass(frozen=True)
class Answer:
    display_text: str
    spoken_segments: tuple[str, ...] = ()
    safety: tuple[SafetyBlock, ...] = ()
    citations: tuple[Citation, ...] = ()
    images: tuple[Image, ...] = ()
    render_version: str = ""
    source_hash: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Answer":
        return cls(
            display_text=d.get("display_text", ""),
            spoken_segments=tuple(d.get("spoken_segments") or ()),
            safety=tuple(SafetyBlock.from_dict(x) for x in d.get("safety") or ()),
            citations=tuple(Citation.from_dict(x) for x in d.get("citations") or ()),
            images=tuple(Image.from_dict(x) for x in d.get("images") or ()),
            render_version=d.get("render_version", ""),
            source_hash=d.get("source_hash", ""),
        )


@dataclass(frozen=True)
class Plan:
    kind: str
    chunk_ids: tuple[int, ...] = ()
    reason: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Plan":
        return cls(kind=d.get("kind", "oos"),
                   chunk_ids=tuple(d.get("chunk_ids") or ()),
                   reason=d.get("reason", ""))


@dataclass(frozen=True)
class Candidate:
    chunk_id: int
    score: float
    content_type: str = ""
    procedure_name: str = ""
    page: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Candidate":
        return cls(chunk_id=d.get("chunk_id", -1),
                   score=float(d.get("score", 0.0)),
                   content_type=d.get("content_type", ""),
                   procedure_name=d.get("procedure_name", ""),
                   page=d.get("page"))


@dataclass(frozen=True)
class Turn:
    plan: Plan
    answer: Optional[Answer] = None
    candidates: tuple[Candidate, ...] = ()
    timing: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Turn":
        raw_answer = d.get("answer")
        return cls(
            plan=Plan.from_dict(d.get("plan") or {}),
            answer=Answer.from_dict(raw_answer) if raw_answer else None,
            candidates=tuple(Candidate.from_dict(x)
                             for x in d.get("candidates") or ()),
            timing=dict(d.get("timing") or {}),
        )
