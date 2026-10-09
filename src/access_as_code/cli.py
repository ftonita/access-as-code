"""access-as-code: init | validate | lint | explain | compile | export-state | diff | review | ..."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from . import __version__
from .changes import compare, render_markdown, render_text
from .compile import compile_access, effective, write
from .demo import make_drifted_state
from .drift import AREAS, diff, unchecked
from .errors import AccessFileError
from .export import ExportError, export_state
from .howto import HOWTO
from .lint import RULES, lint
from .model import load
from .schemas import SCHEMA_V2
from .starter import starter_files


def _today(a: argparse.Namespace) -> date:
    return date.fromisoformat(a.today) if a.today else date.today()


def _cmd_validate(a: argparse.Namespace) -> int:
    acc = load(a.file)
    print(
        f"{a.file}: OK ({len(acc.teams)} teams, {len(acc.people)} people, "
        f"{len(acc.roles)} roles, {len(acc.grants)} grants)"
    )
    return 0


_GITHUB_LEVEL = {"error": "error", "warning": "warning", "info": "notice"}


def _github_annotation(v, acc, path: str) -> str:
    """GitHub Actions workflow command: shows the finding on the offending file in the PR."""
    file = path
    if v.grant is not None and (src := acc.grants[v.grant].source) and Path(path).is_dir():
        file = f"{path.rstrip('/')}/{src}"

    def esc(text: str, *, prop: bool = False) -> str:
        text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return text.replace(":", "%3A").replace(",", "%2C") if prop else text

    return f"::{_GITHUB_LEVEL[v.severity]} file={esc(file, prop=True)},title={v.rule}::{esc(v.message)}"


def _cmd_lint(a: argparse.Namespace) -> int:
    acc = load(a.file)
    violations = lint(acc, _today(a))
    if a.format == "github":
        for v in violations:
            print(_github_annotation(v, acc, a.file))
        errs = sum(v.severity == "error" for v in violations)
        print(f"{errs} error(s), {len(violations) - errs} warning(s)/info")
    elif a.format == "json":
        print(json.dumps([v.__dict__ for v in violations], indent=2))
    else:
        for v in violations:
            print(v)
        errs = sum(v.severity == "error" for v in violations)
        warns = sum(v.severity == "warning" for v in violations)
        print(f"{errs} error(s), {warns} warning(s), {len(violations) - errs - warns} info")
        if errs or warns:
            first = next(v.rule for v in violations if v.severity in ("error", "warning"))
            print(f"Tip: `access-as-code explain {first}` shows how to fix a rule.")
    failing = {"error", "warning"} if a.strict else {"error"}
    return 1 if any(v.severity in failing for v in violations) else 0


def _cmd_compile(a: argparse.Namespace) -> int:
    paths = write(compile_access(load(a.file), _today(a)), a.out)
    print(f"wrote {len(paths)} files to {a.out}")
    return 0


def _cmd_diff(a: argparse.Namespace) -> int:
    desired = compile_access(load(a.file), _today(a)).as_state()
    try:
        actual = json.loads(Path(a.actual).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AccessFileError([f"cannot read {a.actual}: {exc}"]) from exc
    if not isinstance(actual, dict) or not any(area in actual for area in AREAS):
        raise AccessFileError([f"{a.actual}: none of the sections {', '.join(AREAS)} found"])
    drift = diff(desired, actual)
    for d in drift:
        print(d)
    if skipped := unchecked(actual):
        print(f"not checked (absent from snapshot): {', '.join(skipped)}")
    print(f"{len(drift)} difference(s)" if drift else "no drift")
    return 1 if drift else 0


def _cmd_review(a: argparse.Namespace) -> int:
    acc, today = load(a.file), _today(a)
    horizon = today + timedelta(days=a.days)
    rows = [g for g in acc.grants if g.expires and today <= g.expires <= horizon]
    print(f"Grants expiring by {horizon}:")
    for g in sorted(rows, key=lambda g: g.expires):
        print(f"  {g.expires}  {g.describe()}  ticket={g.ticket or '-'}")
    prod_elevated = [
        g
        for g in acc.grants
        if g.env in acc.production and g.role in acc.roles and acc.roles[g.role].elevated
    ]
    print(f"Elevated production grants: {len(prod_elevated)}")
    for g in prod_elevated:
        print(f"  {g.describe()}  expires={g.expires or 'NEVER'}")
    print(f"People with effective access: {len({p for _, p in effective(acc, today)})}")
    return 0


def _cmd_rules(_: argparse.Namespace) -> int:
    for rid, text in RULES.items():
        print(f"{rid}  {text}")
    return 0


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise AccessFileError([f"environment variable {name} is not set"])
    return value


def _cmd_export_state(a: argparse.Namespace) -> int:
    if not (a.vault or a.kubernetes or a.gitlab):
        raise AccessFileError(["choose at least one of --vault, --kubernetes, --gitlab"])
    acc = load(a.file)
    try:
        state = export_state(
            list(acc.teams),
            vault=(_env("VAULT_ADDR"), _env("VAULT_TOKEN")) if a.vault else None,
            kubernetes=a.kubernetes,
            k8s_all=a.k8s_all,
            gitlab=(_env("GITLAB_URL"), _env("GITLAB_TOKEN")) if a.gitlab else None,
            gitlab_prefix=a.gitlab_group_prefix,
            gitlab_missing_ok=a.gitlab_missing_ok,
        )
    except ExportError as exc:
        raise AccessFileError([str(exc)]) from exc
    Path(a.out).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote snapshot ({', '.join(state)}) to {a.out}")
    return 0


def _cmd_explain(a: argparse.Namespace) -> int:
    rid = a.rule.upper()
    if rid not in RULES:
        raise AccessFileError([f"unknown rule '{a.rule}'; run `access-as-code rules` for the list"])
    print(f"{rid}  {RULES[rid]}\n\nHow to fix: {HOWTO[rid]}")
    return 0


def _cmd_init(a: argparse.Namespace) -> int:
    out = Path(a.out)
    expires = str(_today(a) + timedelta(days=30))
    files = starter_files(out.suffix in (".yml", ".yaml"), expires)
    targets = {out if out.suffix in (".yml", ".yaml") else out / name: text for name, text in files.items()}
    if out.suffix not in (".yml", ".yaml") and out.exists() and not out.is_dir():
        raise AccessFileError([f"{out} exists and is not a directory"])
    existing = [str(t) for t in targets if t.exists()]
    if existing:
        raise AccessFileError([f"{', '.join(existing)} already exists; refusing to overwrite"])
    created: list[Path] = []
    try:
        for target, text in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "x", encoding="utf-8") as fh:
                created.append(target)
                fh.write(text)
    except OSError as exc:
        for done in created:
            done.unlink(missing_ok=True)  # leave nothing half-written behind
        raise AccessFileError([f"cannot write {out}: {exc}"]) from exc
    print(f"wrote {', '.join(str(t) for t in targets)}. Next: edit, then `access-as-code lint {out}`")
    return 0


def _cmd_matrix(a: argparse.Namespace) -> int:
    acc = load(a.file)
    cells: dict[tuple[str, str], dict[str, int]] = {}
    for g, _ in effective(acc, _today(a)):
        roles = cells.setdefault((g.team, g.env), {})
        roles[g.role] = roles.get(g.role, 0) + 1
    rows = [["team", *acc.environments]]
    for team in acc.teams:
        row = [team]
        for env in acc.environments:
            roles = sorted(cells.get((team, env), {}).items())
            row.append(", ".join(f"{r} x{n}" for r, n in roles) or "-")
        rows.append(row)
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip())
    return 0


def _cmd_who(a: argparse.Namespace) -> int:
    acc = load(a.file)
    today = _today(a)
    if a.person not in acc.people:
        close = difflib.get_close_matches(a.person, acc.people, n=3)
        hint = f"; did you mean {', '.join(close)}?" if close else ""
        raise AccessFileError([f"unknown person '{a.person}'{hint}"])
    person = acc.people[a.person]
    print(f"{a.person}: team {person.team}, {'active' if person.active else 'OFFBOARDED'}")
    in_force = {g.index for g, pid in effective(acc, today) if pid == a.person}
    rows = [g for g in acc.grants if g.index in in_force]
    for g in sorted(rows, key=lambda g: (g.team, g.env, g.role)):
        via = g.subject if g.is_group else "direct"
        print(
            f"  {g.team}/{g.env}  {g.role}  via {via}  ticket={g.ticket or '-'}  expires={g.expires or '-'}"
        )
    if not rows:
        print("  no effective access")
    for g in acc.grants:
        if g.index not in in_force and a.person in acc.members(g):
            why = f"expired on {g.expires}" if g.expires and g.expires < today else "not in force"
            if not person.active:
                why = "person is offboarded"
            print(f"  NOT IN FORCE ({why}): {g.team}/{g.env}  {g.role}")
    return 0


def _cmd_changes(a: argparse.Namespace) -> int:
    if Path(a.base).exists():
        base = load(a.base)
    elif a.base_may_be_missing:
        base = None  # a brand-new catalog: everything is new
    else:
        raise AccessFileError(
            [f"{a.base} does not exist (pass --base-may-be-missing for a brand-new catalog)"]
        )
    report = compare(base, load(a.head), _today(a))
    changes = report.changes
    if a.format == "json":
        rows = [
            {
                "kind": c.kind,
                "person": c.key[0],
                "team": c.key[1],
                "env": c.key[2],
                "role": c.key[3],
                "old": c.old and c.old.as_dict(),
                "new": c.new and c.new.as_dict(),
            }
            for c in changes
        ]
        out = {"changes": rows, "new_accounts": report.new_accounts, "gone_accounts": report.gone_accounts}
        print(json.dumps(out, indent=2))
    else:
        print((render_markdown if a.format == "markdown" else render_text)(report))
    return 0


def _cmd_schema(_: argparse.Namespace) -> int:
    print(json.dumps(SCHEMA_V2, indent=2))
    return 0


def _cmd_demo_state(a: argparse.Namespace) -> int:
    state = compile_access(load(a.file), _today(a)).as_state()
    Path(a.out).write_text(json.dumps(make_drifted_state(state), indent=2), encoding="utf-8")
    print(f"wrote synthetic drifted snapshot to {a.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="access-as-code", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn, help_: str, *, file: bool = True, today: bool = True) -> argparse.ArgumentParser:
        s = sub.add_parser(name, help=help_)
        if file:
            s.add_argument("file", help="access.yml, or a directory with one .yml file per direction")
        if today:
            s.add_argument("--today", help="YYYY-MM-DD (reproducible runs)")
        s.set_defaults(func=fn)
        return s

    add("validate", _cmd_validate, "schema and structure check", today=False)
    lp = add("lint", _cmd_lint, "least-privilege rules")
    lp.add_argument("--strict", action="store_true", help="warnings fail too")
    lp.add_argument("--format", choices=["text", "json", "github"], default="text")
    add("compile", _cmd_compile, "emit Vault / Kubernetes / GitLab artifacts").add_argument(
        "--out", default="build"
    )
    add("diff", _cmd_diff, "desired vs actual snapshot").add_argument("--actual", required=True)
    add("review", _cmd_review, "expiring and elevated grants").add_argument("--days", type=int, default=30)
    add("rules", _cmd_rules, "list lint rules", file=False, today=False)
    explain = add("explain", _cmd_explain, "how to fix a lint rule", file=False, today=False)
    explain.add_argument("rule", help="e.g. AAC003")
    init = add(
        "init",
        _cmd_init,
        "write a starter declaration (directory; one file if --out ends in .yml)",
        file=False,
    )
    init.add_argument("--out", default="access")
    add("matrix", _cmd_matrix, "who has how many of which roles per team and environment")
    add("who", _cmd_who, "effective access of one person").add_argument("person")
    ch = add("changes", _cmd_changes, "who gained or lost access between two catalogs", file=False)
    ch.add_argument("base", help="the old catalog (file or directory)")
    ch.add_argument(
        "--base-may-be-missing", action="store_true", help="a missing base means a brand-new catalog"
    )
    ch.add_argument("head", help="the new catalog")
    ch.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    add(
        "schema",
        _cmd_schema,
        "print the JSON Schema of version 2 files (editor validation)",
        file=False,
        today=False,
    )
    ex = add(
        "export-state", _cmd_export_state, "read-only export of actual state from live systems", today=False
    )
    ex.add_argument("--out", default="snapshot.json")
    ex.add_argument(
        "--vault", action="store_true", help="policies + identity groups (VAULT_ADDR, VAULT_TOKEN)"
    )
    ex.add_argument("--kubernetes", action="store_true", help="RoleBindings via kubectl (current context)")
    ex.add_argument("--k8s-all", action="store_true", help="also unlabelled RoleBindings to view/edit/admin")
    ex.add_argument("--gitlab", action="store_true", help="group members (GITLAB_URL, GITLAB_TOKEN)")
    ex.add_argument("--gitlab-group-prefix", default="", help="e.g. 'acme/' if team groups live under acme")
    ex.add_argument(
        "--gitlab-missing-ok", action="store_true", help="a team without a GitLab group is not an error"
    )
    add("demo-state", _cmd_demo_state, "write a synthetic drifted snapshot").add_argument(
        "--out", default="actual.json"
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except AccessFileError as exc:
        for problem in exc.problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
