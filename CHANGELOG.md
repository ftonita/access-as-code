# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [1.2.0] - 2026-10-09

### Added
- Version 2 format organised by team (`members`, `access` per environment, `extra` grants, `who` as a list) that
  support staff can edit; version 1 stays supported with identical output.
- Declarations can be split across files: any command takes a directory and merges every `*.yml` (e.g. `common.yml`,
  `web.yml`, `infr.yml`); duplicate definitions are rejected; messages name the file.
- `matrix` (team x environment overview), `who` (effective access of a person), `schema` (JSON Schema for editor
  validation, committed as `schema/access.v2.schema.json`).
- `examples/company/` (two directions, four teams), per-file `examples/CODEOWNERS`, `docs/SUPPORT.md` and
  `docs/SUPPORT.ru.md` cheat sheets for tech support.

### Changed
- `lint --format github` (annotations attached to the file); reusable GitHub Actions workflow `access-check.yml` for
  pull requests (validate, lint, matrix, change preview, compile) and a copy-paste caller
  `examples/ci/github-actions.yml`.
- `init` writes a directory with `common.yml` and a team file (a single file with `--out x.yml`).

## [1.1.0] - 2026-10-09

### Added
- `export-state`: read-only export of the actual state from live Vault, Kubernetes (`kubectl`) and GitLab; `diff`
  skips and reports areas absent from the snapshot.
- `init` writes a lint-clean starter `access.yml`; `explain AAC0xx` shows how to fix a rule; lint prints a hint.
- Russian README (`README.ru.md`) with a language switch in both READMEs; quickstart, recipes, snapshot format,
  FAQ; `examples/ci/gitlab-ci.yml` and `examples/CODEOWNERS`.

### Fixed
- A group member missing from `people` crashed `lint`/`compile` with a `KeyError`; it is now an AAC002 error.
- AAC002 also reports a person whose team is not declared.
- AAC007 reports the actual production environment name and checks each production environment separately.

## [1.0.0] - 2026-10-08

### Added
- `access.yml` schema (JSON Schema 2020-12) and typed model with group resolution.
- 11 lint rules (AAC001-AAC011): sudo ban, reference integrity, production tickets and expiries, elevated roles,
  offboarded people, expired grants, separation of duties, cross-team access, duplicates, unused objects, review window.
- `compile`: Vault HCL policies and identity groups, Kubernetes RoleBindings, GitLab member levels. Output is
  effective access as of the given date.
- `diff`: drift detection against an exported snapshot.
- `review`: expiring and elevated grants.
