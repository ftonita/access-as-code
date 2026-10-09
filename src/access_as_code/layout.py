"""Read an access declaration from one file or from a directory of per-direction files.

Version 1 is the flat format (one file). Version 2 is organised by team and can be split across files,
for example `common.yml` (environments, roles), `web.yml` (teams sites, portal) and `infr.yml` (teams
devops, sys-adm). Every version 2 file is flattened to the version 1 shape and the files are merged, so
lint, compile and diff see one model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import AccessFileError
from .schemas import schema_errors_v2


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps `2026-12-01` a string (validated by the schema) instead of a date object."""


def _no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                f"duplicate key '{key}' (YAML would silently keep only the last one)",
                key_node.start_mark,
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)
_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def read_yaml(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.load(fh, Loader=_Loader)  # noqa: S506 - restricted SafeLoader subclass
    except (OSError, yaml.YAMLError) as exc:
        raise AccessFileError([f"cannot read {path}: {exc}"]) from exc


def list_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return [path]
    files = sorted(
        p
        for p in path.iterdir()
        if p.is_file() and p.suffix in (".yml", ".yaml") and not p.name.startswith(".")
    )
    stems = [f.stem for f in files]
    if dupes := sorted({x for x in stems if stems.count(x) > 1}):
        raise AccessFileError([f"{path}: both .yml and .yaml exist for {', '.join(dupes)}; keep one"])
    if not files:
        raise AccessFileError([f"{path}: no .yml files found"])
    return files


_SINGULAR = {"roles": "role", "people": "person", "groups": "group"}


def _as_list(v: Any) -> list[Any]:
    return list(v) if isinstance(v, list) else [v]


def _options(spec: dict[str, Any]) -> dict[str, Any]:
    return {k: spec[k] for k in ("ticket", "expires", "reason") if k in spec}


def flatten(doc: dict[str, Any], source: str, problems: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Version 2 document -> (version 1 shaped fragment, source file name for each grant)."""
    people: dict[str, Any] = {}
    groups: dict[str, Any] = dict(doc.get("groups", {}))
    grants: list[dict[str, Any]] = []

    def claim(pid: str, team: str, status: str, email: str | None = None) -> None:
        if pid in people:
            problems.append(f"{source}: '{pid}' is listed under both '{people[pid]['team']}' and '{team}'")
        people[pid] = {"team": team, "status": status, **({"email": email} if email else {})}

    for team, t in doc.get("teams", {}).items():
        raw_members = t.get("members", [])
        members = list(raw_members)  # a mapping iterates over its ids
        emails = raw_members if isinstance(raw_members, dict) else {}
        left = t.get("left", [])
        for pid in members:
            claim(pid, team, "active", emails.get(pid))
        for pid in left:
            if pid in members:
                problems.append(f"{source}: teams.{team}: '{pid}' is both in members and in left")
            else:
                claim(pid, team, "offboarded")
        access = t.get("access", {})
        if access and not members:
            problems.append(f"{source}: teams.{team}: 'access' is given but there are no members")
        elif access:
            group = f"{team}-team"
            if group in groups:
                problems.append(f"{source}: group name '{group}' is reserved for the members of '{team}'")
            groups[group] = list(members)
            for env, spec in access.items():
                role, opts = (spec, {}) if isinstance(spec, str) else (spec["role"], _options(spec))
                grants.append({"subject": f"group:{group}", "role": role, "team": team, "env": env, **opts})
        for e in t.get("extra", []):
            for who in _as_list(e["who"]):
                grant = {"subject": who, "role": e["role"], "team": team, "env": e["env"]}
                grants.append({**grant, **_options(e)})
    frag = {
        "teams": list(doc.get("teams", {})),
        "environments": doc.get("environments", []),
        "production_environments": doc.get("production_environments"),
        "settings": {k: doc[k] for k in ("require_email", "email_domains") if k in doc},
        "roles": doc.get("roles", {}),
        "people": people,
        "groups": groups,
        "grants": grants,
    }
    return frag, [source] * len(grants)


def merge(parts: list[tuple[str, dict[str, Any], list[str]]]) -> tuple[dict[str, Any], list[str]]:
    """Combine fragments. Teams, roles, people and groups must be defined in exactly one file."""
    problems: list[str] = []
    out: dict[str, Any] = {
        "version": 1,
        "teams": [],
        "environments": [],
        "roles": {},
        "people": {},
        "groups": {},
        "grants": [],
    }
    settings: dict[str, Any] = {}
    prod: list[str] = []
    prod_given = False
    sources: list[str] = []
    owner: dict[tuple[str, str], str] = {}

    def claim(kind: str, name: str, source: str) -> bool:
        first = owner.setdefault((kind, name), source)
        if first != source:
            problems.append(
                f"{kind} '{name}' is defined in {first} and again in {source}; define it exactly once"
            )
        return first == source

    for source, frag, grant_sources in parts:
        for team in frag["teams"]:
            if claim("team", team, source):
                out["teams"].append(team)
        for env in frag["environments"]:
            if env not in out["environments"]:
                out["environments"].append(env)
        if frag["production_environments"] is not None:
            prod_given = True
            prod.extend(e for e in frag["production_environments"] if e not in prod)
        for kind in ("roles", "people", "groups"):
            for name, value in frag[kind].items():
                if claim(_SINGULAR[kind], name, source):
                    out[kind][name] = value
        for key, value in frag["settings"].items():
            if claim("setting", key, source):
                settings[key] = value
        out["grants"].extend(frag["grants"])
        sources.extend(grant_sources)
    if not out["roles"]:
        problems.append("no roles are defined: add a 'roles:' section (usually in common.yml)")
    if not out["environments"]:
        problems.append(
            "no environments are defined: add 'environments: [dev, stage, prod]' (usually in common.yml)"
        )
    if problems:
        raise AccessFileError(problems)
    out.update(settings)
    if prod_given:
        out["production_environments"] = prod
    return out, sources


def load_doc(path: str) -> tuple[Any, list[str] | None]:
    """-> (version 1 shaped document, source file per grant or None for a plain version 1 file)."""
    p = Path(path)
    files = list_files(p)
    docs = [(f, read_yaml(f)) for f in files]
    is_v2 = [isinstance(d, dict) and d.get("version") == 2 for _, d in docs]
    if not p.is_dir() and not is_v2[0]:
        return docs[0][1], None
    problems: list[str] = []
    parts = []
    for (f, d), ok in zip(docs, is_v2, strict=True):
        name = f.name if p.is_dir() else str(f)
        if not ok:
            problems.append(
                f"{name}: files in a directory must declare 'version: 2' (flat version 1 works alone)"
            )
            continue
        errs = schema_errors_v2(d)
        problems.extend(f"{name}: {e}" for e in errs)
        if not errs:
            frag, srcs = flatten(d, name, problems)
            parts.append((name, frag, srcs))
    if problems:
        raise AccessFileError(problems)
    return merge(parts)
