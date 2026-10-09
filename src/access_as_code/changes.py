"""Who gained or lost access between two versions of the catalog (typically base branch vs pull request)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .compile import effective
from .model import Access

Key = tuple[str, str, str, str]  # person, team, env, role


@dataclass(frozen=True)
class Detail:
    via: tuple[str, ...]  # "direct" or "group:<name>"
    tickets: tuple[str, ...]
    expires: date | None  # latest expiry among the grants giving this access; None = never

    def as_dict(self) -> dict:
        return {
            "via": list(self.via),
            "tickets": list(self.tickets),
            "expires": str(self.expires or "") or None,
        }

    def text(self) -> str:
        parts = [", ".join(self.via)]
        if self.tickets:
            parts.append("ticket " + ", ".join(self.tickets))
        parts.append(f"until {self.expires}" if self.expires else "no expiry")
        return "; ".join(parts)


@dataclass(frozen=True)
class Change:
    kind: str  # gained | lost | changed
    key: Key
    old: Detail | None
    new: Detail | None

    @property
    def person(self) -> str:
        return self.key[0]


def entitlements(acc: Access | None, today: date) -> dict[Key, Detail]:
    if acc is None:
        return {}
    grouped: dict[Key, list] = {}
    for g, pid in effective(acc, today):
        grouped.setdefault((pid, g.team, g.env, g.role), []).append(g)
    out = {}
    for key, grants in grouped.items():
        expiries = [g.expires for g in grants]
        out[key] = Detail(
            tuple(sorted({g.subject if g.is_group else "direct" for g in grants})),
            tuple(sorted({g.ticket for g in grants if g.ticket})),
            None if None in expiries else max(expiries),
        )
    return out


@dataclass(frozen=True)
class Report:
    changes: list[Change]
    new_accounts: list[str]  # people with access now and none before: local accounts to create
    gone_accounts: list[str]  # people with no access left: local accounts to remove


def _needs_account(acc: Access | None, key: Key) -> bool:
    """Does this access involve a system (Vault, Kubernetes, GitLab) where the person needs an account?"""
    role = acc.roles[key[3]] if acc else None
    return bool(role and (role.vault or role.kubernetes or role.gitlab))


def compare(base: Access | None, head: Access | None, today: date) -> Report:
    """Gained and lost access, plus access whose expiry or source changed. Sorted by person."""
    old, new = entitlements(base, today), entitlements(head, today)
    before = {k[0] for k in old if _needs_account(base, k)}
    after = {k[0] for k in new if _needs_account(head, k)}
    changes = [Change("gained", k, None, new[k]) for k in new.keys() - old.keys()]
    changes += [Change("lost", k, old[k], None) for k in old.keys() - new.keys()]
    changes += [Change("changed", k, old[k], new[k]) for k in old.keys() & new.keys() if old[k] != new[k]]
    order = {"gained": 0, "lost": 1, "changed": 2}
    ordered = sorted(changes, key=lambda c: (c.person, c.key[1:], order[c.kind]))
    return Report(ordered, sorted(after - before), sorted(before - after))


SIGN = {"gained": "+", "lost": "-", "changed": "~"}


def _accounts(report: Report) -> list[tuple[str, str]]:
    out = []
    if report.new_accounts:
        out.append(("New accounts to create", ", ".join(report.new_accounts)))
    if report.gone_accounts:
        out.append(("Accounts no longer needed", ", ".join(report.gone_accounts)))
    return out


def render_text(report: Report) -> str:
    changes = report.changes
    if not changes:
        return "No change in effective access."
    lines = []
    for person in dict.fromkeys(c.person for c in changes):
        lines.append(person)
        for c in (c for c in changes if c.person == person):
            _, team, env, role = c.key
            if c.kind == "changed":
                detail = f"was: {c.old.text()}  ->  now: {c.new.text()}"
            else:
                detail = (c.new or c.old).text()
            lines.append(f"  {SIGN[c.kind]} {team}/{env}  {role}  ({detail})")
    gained = sum(c.kind == "gained" for c in changes)
    lost = sum(c.kind == "lost" for c in changes)
    lines.append(f"{gained} gained, {lost} lost, {len(changes) - gained - lost} changed")
    return "\n".join([*lines, *(f"{label}: {names}" for label, names in _accounts(report))])


def render_markdown(report: Report) -> str:
    changes = report.changes
    if not changes:
        return "No change in effective access."
    rows = ["| | Person | Team/env | Role | Details |", "|---|---|---|---|---|"]
    for c in changes:
        person, team, env, role = c.key
        icon = {"gained": "➕ gained", "lost": "➖ lost", "changed": "✏️ changed"}[c.kind]
        detail = f"{c.old.text()} → {c.new.text()}" if c.kind == "changed" else (c.new or c.old).text()
        rows.append(f"| {icon} | `{person}` | {team}/{env} | {role} | {detail} |")
    extra = [f"**{label}:** {names}" for label, names in _accounts(report)]
    return "\n".join([*rows, "", *extra]) if extra else "\n".join(rows)
