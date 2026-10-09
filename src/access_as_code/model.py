"""Typed view of a schema-valid access.yml, with group resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .errors import AccessFileError
from .layout import load_doc
from .schemas import schema_errors


@dataclass(frozen=True)
class Role:
    name: str
    vault: tuple[str, ...] = ()
    kubernetes: str | None = None
    gitlab: str | None = None

    @property
    def elevated(self) -> bool:
        return "delete" in self.vault or "sudo" in self.vault or self.kubernetes == "admin"


@dataclass(frozen=True)
class Person:
    id: str
    team: str
    active: bool


@dataclass(frozen=True)
class Grant:
    index: int
    subject: str
    role: str
    team: str
    env: str
    expires: date | None = None
    ticket: str | None = None
    reason: str | None = None
    source: str | None = None  # file the grant was written in (set for version 2 files)

    @property
    def is_group(self) -> bool:
        return self.subject.startswith("group:")

    @property
    def subject_name(self) -> str:
        return self.subject.removeprefix("group:")

    def describe(self) -> str:
        text = f"grant #{self.index} ({self.subject} -> {self.role} on {self.team}/{self.env})"
        return f"{text} [{self.source}]" if self.source else text


@dataclass(frozen=True)
class Access:
    teams: tuple[str, ...]
    environments: tuple[str, ...]
    production: tuple[str, ...]
    roles: dict[str, Role]
    people: dict[str, Person]
    groups: dict[str, tuple[str, ...]]
    grants: tuple[Grant, ...]

    def members(self, grant: Grant) -> tuple[str, ...]:
        """People a grant applies to. Unknown subjects/members resolve to nobody (`lint` reports AAC002)."""
        if grant.is_group:
            return tuple(p for p in self.groups.get(grant.subject_name, ()) if p in self.people)
        return (grant.subject_name,) if grant.subject_name in self.people else ()


def parse(doc: Any, sources: list[str] | None = None) -> Access:
    problems = schema_errors(doc)
    if problems:
        raise AccessFileError(problems)
    roles = {
        n: Role(n, tuple(r.get("vault", ())), r.get("kubernetes"), r.get("gitlab"))
        for n, r in doc["roles"].items()
    }
    people = {n: Person(n, p["team"], p["status"] == "active") for n, p in doc["people"].items()}
    grants = tuple(
        Grant(
            i,
            g["subject"],
            g["role"],
            g["team"],
            g["env"],
            date.fromisoformat(g["expires"]) if "expires" in g else None,
            g.get("ticket"),
            g.get("reason"),
            sources[i] if sources else None,
        )
        for i, g in enumerate(doc["grants"])
    )
    return Access(
        tuple(doc["teams"]),
        tuple(doc["environments"]),
        tuple(doc.get("production_environments", ["prod"])),
        roles,
        people,
        {k: tuple(v) for k, v in doc.get("groups", {}).items()},
        grants,
    )


def load(path: str) -> Access:
    """Load a version 1 file, a version 2 file, or a directory of version 2 files."""
    doc, sources = load_doc(path)
    try:
        return parse(doc, sources)
    except AccessFileError:
        raise
    except ValueError as exc:  # bad date etc.
        raise AccessFileError([str(exc)]) from exc
