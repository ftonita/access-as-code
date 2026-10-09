# access-as-code

**English** | [Русский](README.ru.md)

[![ci](https://github.com/ftonita/access-as-code/actions/workflows/ci.yml/badge.svg)](https://github.com/ftonita/access-as-code/actions)
![Vault](https://img.shields.io/badge/Vault-policies-FFEC6E?logo=vault&logoColor=black)
![Kubernetes](https://img.shields.io/badge/Kubernetes-RBAC-326CE5?logo=kubernetes&logoColor=white)
![GitLab](https://img.shields.io/badge/GitLab-members-FC6D26?logo=gitlab&logoColor=white)

**Declare who may do what in one reviewed YAML file. Lint it against least-privilege rules, compile it to Vault policies, Kubernetes RBAC and GitLab membership, and detect drift from what is actually configured.**

Access that lives in click-ops UIs cannot be reviewed, diffed or audited. Here every change is a merge request: reviewers see exactly which person gets which role on which team and environment, CI rejects risky grants, and the same file generates the configuration for all three systems.

> **All people, teams, tickets and tenants are synthetic.** This is a reference design for a least-privilege access model, not data or code from any employer.

## Quickstart (10 minutes)

Requires Python 3.10+. Not on PyPI yet, install from a checkout:

```bash
git clone https://github.com/ftonita/access-as-code.git && cd access-as-code
python -m venv .venv && source .venv/bin/activate
pip install -e .

access-as-code init --out access          # starter files in ./access (common.yml + one team file)
access-as-code lint access                # exit 0 = OK, 1 = rule errors, 2 = bad input
access-as-code matrix access              # who has which roles where, at a glance
access-as-code compile access --out build # what would be applied to Vault / Kubernetes / GitLab
```

Or play with the bundled example, a company split into two directions: `examples/company/` (clean, a good template) and, in the older flat format, `examples/access.bad.yml` (one planted problem per rule).
Lint failed? `access-as-code explain AAC003` tells you how to fix that rule.

**Who edits what?** Tech support edits the YAML following [the support cheat sheet](docs/SUPPORT.md) (copy-paste recipes for the usual tickets). Security owns `common.yml`. Each direction lead reviews their own file. CI does the rest.

## The model: one screen per team

```yaml
# web.yml - direction "web"
version: 2
teams:
  sites:
    members:                                 # everyone in the team: login -> corporate email
      alice: alice@corp.example
      bob: bob@corp.example
    access:                                  # what EVERY member gets, per environment
      dev: developer
      stage: developer
      prod: { role: viewer, ticket: SEC-101 }
    extra:                                   # one-off / temporary access
      - { who: alice, role: deployer, env: prod, ticket: SEC-110, expires: 2026-12-15 }
      - { who: [bob, carol], role: viewer, env: stage }
```

| Concept | Meaning |
|---|---|
| **role** | a named bundle of rights for each system (defined once in `common.yml`): "developer" means the same in Vault, Kubernetes and GitLab |
| **members** | the people of the team. Removing a name revokes the team-wide access; move it to `left:` to also make lint catch leftovers in `extra` |
| **access** | the team matrix: environment -> role (or `{ role, ticket }`). Applies to every member |
| **extra** | individual grants: `who` (one name or a list), `role`, `env`, optional `ticket`, `expires`, `reason`. The team that owns the resource is the one that lists the entry, even if the person belongs to another team |

```yaml
    members:                       # login: corporate email
      alice: alice@corp.example
      bob: bob@corp.example
```

Rules of thumb: production always needs a `ticket`; a grant to a person in production needs `expires` (max 90 days); the dangerous `break-glass` role needs both and at most 7 days.

## Splitting into files by direction

Pass a **directory** and every `*.yml` in it is merged, so each direction gets its own file and its own reviewers:

```text
access/
  common.yml   # environments, production_environments, roles                  owner: security
  web.yml      # teams: sites, portal                                          owner: web leads
  infr.yml     # teams: devops, sys-adm                                        owner: infra leads
```

* Commands take either a file or the directory: `access-as-code lint access/`.
* A team, person, group or role is defined **exactly once**, in one file; defining it twice is an error that names both files. Environments and `production_environments` are merged.
* Order of files does not matter. Messages carry the file name: `AAC003 error: grant #4 (...) [web.yml]: production grant without a ticket`.
* Access that spans directions is written in the file that owns the resource: if alice (web) needs stage in devops, the entry goes under `devops.extra` in `infr.yml`. The infra leads approve it (see [examples/CODEOWNERS](examples/CODEOWNERS)); without a ticket lint warns about cross-team access (AAC008).
* Files in a directory must be `version: 2`. A single file may contain everything (`common` + teams), which is fine for a small company.
* Editor help: every example starts with `# yaml-language-server: $schema=...`; the schema lives in [schema/access.v2.schema.json](schema/access.v2.schema.json) (`access-as-code schema` regenerates it), so VS Code / JetBrains with a YAML plugin autocomplete and underline mistakes while typing.

## Commands

`PATH` is a file or a directory.

| Command | What it does | Exit code |
|---|---|---|
| `init [--out access]` | starter files (a directory; a single file if `--out` ends in `.yml`); never overwrites | 0 / 2 |
| `validate PATH` | schema and structure only | 0 / 2 |
| `lint PATH [--strict] [--format text, json or github]` | least-privilege rules; `--strict` fails on warnings too; `github` prints annotations attached to the offending file in the PR | 0 / 1 |
| `explain AAC003` | what a rule means and how to fix it | 0 / 2 |
| `matrix PATH` | table team x environment: which roles, how many people | 0 |
| `who PATH PERSON` | all effective access of one person, where it comes from, tickets and expiry | 0 / 2 |
| `changes BASE HEAD [--format text, markdown or json]` | who gained or lost access between two catalogs (e.g. the base branch and a PR), plus accounts to create or remove | 0 / 2 |
| `compile PATH [--out build]` | write Vault / Kubernetes / GitLab artifacts and `people.json` | 0 |
| `export-state PATH --vault --kubernetes --gitlab [--out snapshot.json]` | read-only export of the actual state from live systems | 0 / 2 |
| `diff PATH --actual snapshot.json` | desired vs actual state (areas missing from the snapshot are reported as not checked) | 0 no drift / 1 drift |
| `review PATH [--days 30]` | expiring and elevated grants | 0 |
| `schema` | JSON Schema of version 2 files (editor validation) | 0 |
| `rules` | list all rules | 0 |
| `demo-state PATH [--out actual.json]` | fabricate a drifted snapshot for experiments | 0 |

Every command that depends on time takes `--today YYYY-MM-DD` (default: the real date). Exit code 2 means the input could not be read or failed the schema; the message names the file and the exact path, e.g. `web.yml: teams.sites.extra[1]: 'env' is a required property`.

> **Dates and the examples.** Example grants expire in Oct-Dec 2026. Run them with `--today 2026-10-08` (as this README and CI do) or they will start to fail as "expired" later.

## Everyday recipes

Full copy-paste versions with the CI messages you will see are in [docs/SUPPORT.md](docs/SUPPORT.md). In short, every request is a small edit of one team block:

| Ticket says... | Edit |
|---|---|
| New employee | add `login: email` to `members` of the team (the address is where their account credentials are sent) |
| Employee left | move the name from `members` to `left`; delete their lines in `extra` |
| Temporary prod access | add a line to `extra` with `ticket` and `expires` |
| Emergency access | the same with role `break-glass`, `expires` within 7 days, a `reason` |
| Extend / remove access | change `expires` / delete the line |
| New team | add a block under `teams:` (in the file of its direction; the Vault mount `kv-<team>` and Kubernetes namespaces `<team>-<env>` must exist) |
| New role | security adds it to `common.yml` |

## Conventions the tool relies on

* **Names** (`teams`, `environments`, roles, people, groups) are lowercase letters, digits and dashes.
* **Team baseline = group `<team>-team`.** Version 2 turns `members` + `access` into a group of that name (visible in lint messages as `group:sites-team`); do not define a group with that name yourself.
* **Person id = login in the target systems.** It becomes the `User` name in Kubernetes RoleBindings (your OIDC username), the member in Vault identity groups and the key in GitLab `members.json`. If your IdP uses `a.smith`, rename or map it in your apply step.
* **Naming convention for targets:** Vault policy/group `<team>-<env>-<role>`, KV path `kv-<team>/data|metadata/<env>/*`, Kubernetes namespace `<team>-<env>`, RoleBinding `aac-<level>` bound to the built-in ClusterRole `view`/`edit`/`admin`.
* **AAC007 matches role names** `deployer` and `approver`. If you call them differently, the rule will not fire (see `SOD_ROLES` in `src/access_as_code/lint.py`).
* A group grant gives every member the role; two grants to the same person in the same place merge (the highest GitLab/Kubernetes level wins, Vault gets one policy per role).

## Lint rules (`access-as-code rules`)

| ID | Severity | Rule |
|---|---|---|
| AAC001 | error | No role may hold the Vault `sudo` capability. |
| AAC002 | error | References resolve: grants to known teams, environments, roles and subjects; group members to people; people to teams. |
| AAC003 | error | Production grants need a ticket; direct person grants also need an expiry (max 90 days). |
| AAC004 | error | Elevated roles (`delete` / Kubernetes `admin`) in production need a ticket and expire within 7 days. |
| AAC005 | error | Offboarded people hold no access, directly or via a group. |
| AAC006 | error | Expired grants must be removed. |
| AAC007 | error | Separation of duties: nobody is both `deployer` and `approver` on one team in production, even through groups. |
| AAC008 | warning | Cross-team access needs a ticket. |
| AAC009 | warning | Duplicate grants. |
| AAC010 | info | Unused roles and groups. |
| AAC011 | warning | Grants expiring within 14 days are due for review. |
| AAC012 | error | With `require_email: true`, every active person has a corporate email. |
| AAC013 | error | Two people never share one email address. |
| AAC014 | error | With `email_domains`, emails belong to one of the listed domains. |

`lint` exits 1 on errors (`--strict`: also on warnings), so it works as a required merge-request check. `--today` pins the date for reproducible runs.

## Walkthrough on the bundled synthetic data

```text
$ access-as-code lint examples/access.bad.yml --today 2026-10-08
AAC001 error: role 'super-ops' grants the Vault 'sudo' capability
AAC003 error: grant #3 (bob -> deployer on payments/prod): direct production grant without an expiry
AAC005 error: grant #0 (group:payments-devs -> developer on payments/dev): 'gone' is offboarded
AAC007 error: 'alice' is both deployer and approver on payments/prod
...
14 error(s), 5 warning(s), 3 info                                   (exit 1)

$ access-as-code lint examples/company --today 2026-10-08
AAC011 warning: grant #5 (erin -> break-glass on devops/prod) [infr.yml]: expires on 2026-10-12
0 error(s), 1 warning(s), 0 info                                    (exit 0)

$ access-as-code matrix examples/company --today 2026-10-08
team     dev           stage                    prod
devops   developer x2  developer x2             approver x1, break-glass x1, deployer x1, viewer x2
sys-adm  developer x2  developer x2             approver x1, deployer x1, viewer x2
sites    developer x2  developer x2, viewer x1  approver x1, deployer x1, viewer x2
portal   developer x2  developer x2             approver x1, deployer x1, viewer x2

$ access-as-code who examples/company carol --today 2026-10-08
carol: team portal, active
  portal/dev  developer  via group:portal-team  ticket=-  expires=-
  portal/prod  deployer  via direct  ticket=SEC-112  expires=2026-12-01
  portal/prod  viewer  via group:portal-team  ticket=SEC-102  expires=-
  portal/stage  developer  via group:portal-team  ticket=-  expires=-
  sites/stage  viewer  via direct  ticket=SEC-130  expires=-

$ access-as-code compile examples/company --today 2026-10-08 --out build
wrote 39 files to build
```

Generated, for example `build/vault/policies/sites-prod-deployer.hcl`:

```hcl
path "kv-sites/data/prod/*" {
  capabilities = ["create", "read", "update"]
}

path "kv-sites/metadata/prod/*" {
  capabilities = ["list", "read"]
}
```

plus `vault/groups.json` (identity group -> policy + members), one Kubernetes `RoleBinding` per namespace and level (`sites-dev` / `edit`) and `gitlab/members.json` (highest level per person per team).

**Compile emits effective access only**: expired grants, offboarded people and invalid grants never reach the output, even if lint was skipped.

### Drift

```text
$ access-as-code diff examples/company --today 2026-10-08 --actual actual.json
changed  vault_policies:devops-dev-developer  content differs
extra    vault_policies:legacy-admin  configured but not declared
changed  vault_groups:devops-dev-developer  missing members ['erin']
changed  vault_groups:devops-prod-break-glass  extra members ['zed']
missing  kubernetes:devops-dev/edit  declared but not configured
changed  gitlab:sites  carol: declared 'reporter', actual 'maintainer'
6 difference(s)                                                      (exit 1)
```

### Exporting the actual state from live systems

```bash
export VAULT_ADDR=https://vault.example.com VAULT_TOKEN=...      # needs list/read on sys/policies/acl and identity/*
export GITLAB_URL=https://gitlab.example.com GITLAB_TOKEN=...     # read_api scope, member of the team groups
access-as-code export-state access --vault --kubernetes --gitlab --out snapshot.json
access-as-code diff access --actual snapshot.json
```

* **Read-only**: only GET/LIST requests and `kubectl get`. Tokens are read from the environment and never written to the snapshot. Use a dedicated read-only token.
* **Vault**: all ACL policies except `default`/`root`, and all identity groups with their entity *names* (entity name must equal the person id). `VAULT_CACERT` is honoured.
* **Kubernetes**: `kubectl` with your current context. By default only RoleBindings labelled `managed-by=access-as-code` (what `compile` generates) are read; add `--k8s-all` to also catch hand-made RoleBindings to `view`/`edit`/`admin`.
* **GitLab**: *direct* members of the group `<prefix><team>` (`--gitlab-group-prefix 'acme/'`); guest/owner levels are exported as is, so an owner shows up as drift. A team without a group is reported as missing.
* * Safety: HTTPS is required (plain `http://` only for localhost), redirects are never followed, `VAULT_NAMESPACE` is honoured. A group member whose Vault entity was deleted appears as `<unknown-entity:id>`; Kubernetes Group/ServiceAccount subjects appear as `group:<name>` / `serviceaccount:<ns>:<name>` so over-privilege shows up as extra members; GitLab inherited (parent-group) members are not listed.
* A missing GitLab group is an error (wrong prefix or token?) unless `--gitlab-missing-ok`.
* Pass only the systems you can reach: the others are listed as `not checked`, not as drift.

This is covered by tests against a fake Vault/GitLab and a fake `kubectl`, **not against real instances**.

To reproduce the sample output without any live system: `access-as-code demo-state examples/company --today 2026-10-08 --out actual.json` fabricates plausible hand-made changes. In real use you export the same four sections from your systems on a schedule and fail the job on any difference. Easiest way to learn the format: `compile` writes the "desired" side, and `demo-state` writes a complete example snapshot. Shape of the snapshot:

```json
{
  "vault_policies": { "sites-dev-developer": "<HCL text, as in build/vault/policies/*.hcl>" },
  "vault_groups":   { "sites-dev-developer": ["alice", "bob"] },
  "kubernetes":     { "sites-dev/edit": ["alice", "bob"] },
  "gitlab":         { "sites": { "alice": "maintainer" } }
}
```

A snapshot with none of the four sections is rejected (exit 2). A section that is absent from the snapshot is not checked; an empty one (`{}`) means "nothing configured" and reports everything declared as missing.

## Suggested workflow

1. The `access/` directory lives in a repo with CODEOWNERS: one owner group per file (security for `common.yml`, the direction leads for their file).
2. Merge request: CI runs `lint` (blocking) and shows `review`.
3. After merge: `compile`, apply with your tooling (Terraform Vault provider, `kubectl apply`, GitLab API).
4. Nightly: `export-state` then `diff`; page on drift.

## Corporate email and personal delivery of account credentials

Some systems need **local accounts** (Vault userpass, local GitLab users, Kubernetes client certificates...). To create them without keeping a password, token or any other secret in the repository, a person has a corporate address and the automation sends the credentials to that mailbox, personally and once:

```yaml
# common.yml
require_email: true                 # AAC012: every active person needs an address
email_domains: [corp.example]       # AAC014: and only a corporate one
# web.yml
    members:
      alice: alice@corp.example     # login: address (bob: with no address is allowed unless require_email is on)
```

* `compile` writes **`people.json`**: for every person who has effective access it lists `email`, `team`, the `systems` that need an account (`vault`, `kubernetes`, `gitlab`, derived from the roles) and the `access` they get. It contains **no secrets**. The new `changes` command lists the **new accounts to create** and the **accounts no longer needed** in a PR, so the automation knows whom to onboard and offboard.
* The sending step is yours (it needs your mail relay and your account-creation tooling) and this tool never handles a password. Recommended pattern: generate a one-time password or an invitation/reset link, send it to `people.json` -> `email` from the pipeline, force a change at first login, and keep the secret in no log, artifact or variable.
* Lint protects the destination: a private domain (AAC014) or a mailbox shared by two people (AAC013) fails the PR, and messages name the person, never the address. The address is personal data: keep the access repository **private** and treat `people.json` as confidential.

## Pull request check (GitHub Actions)

Copy [examples/ci/github-actions.yml](examples/ci/github-actions.yml) to `.github/workflows/access.yml` of your access repository (5 lines of configuration). It calls the reusable workflow [.github/workflows/access-check.yml](.github/workflows/access-check.yml), which on every PR that touches `access/`:

* validates and lints; findings show up as **annotations on the offending file** and block the merge (`strict: true` also blocks on warnings);
* writes a **job summary** with the team x environment matrix, expiring/elevated grants, **who gained or lost access** (and which accounts to create or remove) and a `diff` of the generated Vault / Kubernetes / GitLab configuration between the base branch and the PR, so a reviewer sees what merging would really change;
* checks that the catalog compiles. It is read-only and needs no secrets (`permissions: contents: read`).

Make the check **required** (branch protection / ruleset) and add CODEOWNERS so each direction's file needs its own leads' approval. This repository dogfoods it in `.github/workflows/access-pr.yml`. Pin the `uses:` ref to a tag or commit SHA if you want to control updates.

## Flat format (version 1)

The original single-file format (`version: 1`: `people`, `groups` and a list of `grants`, each with `subject`, `role`, `team`, `env`) is still supported and produces exactly the same output; see `examples/access.yml` and `examples/access.bad.yml`. New work should use version 2, which is shorter and can be split by direction. Both are internally turned into the same model.

## FAQ

* **`error: ... is a required property`** - the file failed the schema; `access-as-code validate` prints every problem with its path.
* **Lint passes locally but fails in CI** - dates: pin both with `--today`, or fix the grant that is about to expire (AAC011 warns 14 days ahead).
* **Does `compile` change my systems?** No. It only writes files; applying them (Terraform, `kubectl apply`, GitLab API) is your step.
* **Can I skip a rule for one grant?** No, by design. Change the rule in code via a reviewed PR or fix the grant.

## What is verified

Reproduce with `pip install -e ".[dev]" && pytest` (106 tests): every lint rule (positive, negative and boundary cases such as an expiry exactly 90 days away or a grant expiring today), schema rejection, group resolution, deterministic compilation, exclusion of expired/offboarded access, drift of every kind, CLI exit codes.

**Not verified:** applying the output to real Vault, Kubernetes or GitLab instances; the HCL, RoleBinding and member-level formats follow the public documentation but were never loaded into those systems. `export-state` was tested against fakes only; objects Vault returns for namespaces other than the token's, nested GitLab subgroups and inherited memberships are not exported. Vault policy paths assume KV v2 mounts named `kv-<team>`. The merge of several files and the version 2 flattening are covered by tests (duplicate definitions, ordering, error messages with file names). Roles are per-team and per-environment; finer scoping (single paths, time-of-day) is out of scope.
