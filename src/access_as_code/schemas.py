"""Structural schema for access.yml (Draft 2020-12)."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

NAME = {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"}
EMAIL = r"^[^@\s,;<>]+@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$"
DOMAIN = r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$"
# Settings for the corporate address used to deliver local-account credentials personally.
EMAIL_SETTINGS = {
    "require_email": {"type": "boolean"},
    "email_domains": {
        "type": "array",
        "minItems": 1,
        "uniqueItems": True,
        "items": {"type": "string", "pattern": DOMAIN},
    },
}
CAPS = {"enum": ["create", "read", "update", "delete", "list", "sudo"]}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["version", "teams", "environments", "roles", "people", "grants"],
    "additionalProperties": False,
    "properties": {
        "version": {"const": 1},
        "teams": {"type": "array", "minItems": 1, "items": NAME, "uniqueItems": True},
        "environments": {"type": "array", "minItems": 1, "items": NAME, "uniqueItems": True},
        "production_environments": {"type": "array", "items": NAME, "default": ["prod"]},
        **EMAIL_SETTINGS,
        "roles": {
            "type": "object",
            "minProperties": 1,
            "propertyNames": NAME,
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string"},
                    "vault": {"type": "array", "items": CAPS, "uniqueItems": True},
                    "kubernetes": {"enum": ["view", "edit", "admin"]},
                    "gitlab": {"enum": ["reporter", "developer", "maintainer"]},
                },
            },
        },
        "people": {
            "type": "object",
            "propertyNames": NAME,
            "additionalProperties": {
                "type": "object",
                "required": ["team", "status"],
                "additionalProperties": False,
                "properties": {
                    "team": NAME,
                    "status": {"enum": ["active", "offboarded"]},
                    "email": {"type": "string", "pattern": EMAIL},
                },
            },
        },
        "groups": {
            "type": "object",
            "propertyNames": NAME,
            "additionalProperties": {"type": "array", "items": NAME, "minItems": 1},
        },
        "grants": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["subject", "role", "team", "env"],
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string", "pattern": "^(group:)?[a-z][a-z0-9-]*$"},
                    "role": NAME,
                    "team": NAME,
                    "env": NAME,
                    "expires": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "ticket": {"type": "string", "pattern": "^[A-Z]+-\\d+$"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


SUBJECT = "^(group:)?[a-z][a-z0-9-]*$"
_GRANT_OPTIONS = {
    "ticket": {"type": "string", "pattern": "^[A-Z]+-\\d+$"},
    "expires": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    "reason": {"type": "string"},
}

# Version 2: one file per direction (web, infr, ...). A team lists its members, what every member gets per
# environment (`access`) and one-off grants (`extra`). Keywords that do not apply to a value's type are
# ignored by JSON Schema, so one entry can accept both `dev: developer` and `prod: {role: ..., ticket: ...}`.
SCHEMA_V2: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "access-as-code declaration, version 2",
    "type": "object",
    "required": ["version"],
    "additionalProperties": False,
    "properties": {
        "version": {"const": 2},
        "environments": SCHEMA["properties"]["environments"],
        "production_environments": SCHEMA["properties"]["production_environments"],
        **EMAIL_SETTINGS,
        "roles": SCHEMA["properties"]["roles"],
        "groups": SCHEMA["properties"]["groups"],
        "teams": {
            "type": "object",
            "propertyNames": NAME,
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    # a list of ids, or a mapping id -> corporate email (null = no address yet)
                    "members": {
                        "type": ["array", "object"],
                        "items": NAME,
                        "uniqueItems": True,
                        "propertyNames": NAME,
                        "additionalProperties": {"type": ["string", "null"], "pattern": EMAIL},
                    },
                    "left": {"type": "array", "items": NAME, "uniqueItems": True},
                    "access": {
                        "type": "object",
                        "propertyNames": NAME,
                        "additionalProperties": {
                            "type": ["string", "object"],
                            "pattern": NAME["pattern"],
                            "required": ["role"],
                            "additionalProperties": False,
                            "properties": {"role": NAME, **_GRANT_OPTIONS},
                        },
                    },
                    "extra": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["who", "role", "env"],
                            "additionalProperties": False,
                            "properties": {
                                "who": {
                                    "type": ["string", "array"],
                                    "pattern": SUBJECT,
                                    "minItems": 1,
                                    "items": {"type": "string", "pattern": SUBJECT},
                                },
                                "role": NAME,
                                "env": NAME,
                                **_GRANT_OPTIONS,
                            },
                        },
                    },
                },
            },
        },
    },
}


def _errors(schema: dict[str, Any], doc: Any) -> list[str]:
    v = Draft202012Validator(schema)
    out = []
    for e in v.iter_errors(doc):
        path = ""
        for p in e.absolute_path:
            path += f"[{p}]" if isinstance(p, int) else (f".{p}" if path else str(p))
        out.append(f"{path or '<root>'}: {e.message}")
    return sorted(out)


def schema_errors(doc: Any) -> list[str]:
    return _errors(SCHEMA, doc)


def schema_errors_v2(doc: Any) -> list[str]:
    return _errors(SCHEMA_V2, doc)
