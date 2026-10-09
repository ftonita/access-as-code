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

Requires Python 3.10+. The package is not on PyPI yet, install from a checkout:

```bash
git clone https://github.com/ftonita/access-as-code.git && cd access-as-code
python -m venv .venv && source .venv/bin/activate
pip install -e .

access-as-code init --out access.yml      # starter file that lints clean
access-as-code lint access.yml            # exit 0 = OK, 1 = rule errors, 2 = bad input
access-as-code compile access.yml --out build
ls -R build                               # what would be applied to Vault / Kubernetes / GitLab
```

Or skip `init` and play with the bundled files: `examples/access.yml` (clean) and `examples/access.bad.yml` (one planted problem per rule).
Lint failed? `access-as-code explain AAC003` tells you how to fix that rule.

**Where do I put it in a real company?** In a dedicated Git repo (or folder) with `access.yml`, CODEOWNERS ([examples/CODEOWNERS](examples/CODEOWNERS)) and a CI job ([examples/ci/gitlab-ci.yml](examples/ci/gitlab-ci.yml); GitHub: see `.github/workflows/ci.yml`, job `access-review`).

## Commands

| Command | What it does | Exit code |
|---|---|---|
| `init [--out access.yml]` | write a starter file (refuses to overwrite) | 0 / 2 |
| `validate FILE` | schema and structure only | 0 / 2 |
| `lint FILE [--strict] [--format json]` | least-privilege rules; `--strict` fails on warnings too | 0 / 1 |
| `explain AAC003` | what a rule means and how to fix it | 0 / 2 |
| `compile FILE [--out build]` | write Vault / Kubernetes / GitLab artifacts | 0 |
| `export-state FILE --vault --kubernetes --gitlab [--out snapshot.json]` | read-only export of the actual state from live systems | 0 / 2 |
| `diff FILE --actual snapshot.json` | desired vs actual state (areas missing from the snapshot are reported as not checked) | 0 no drift / 1 drift |
| `review FILE [--days 30]` | expiring and elevated grants | 0 |
| `rules` | list all rules | 0 |
| `demo-state FILE [--out actual.json]` | fabricate a drifted snapshot for experiments | 0 |

Every command that depends on time takes `--today YYYY-MM-DD` (default: the real date). Exit code 2 means the input could not be read or failed the schema; the message names the exact path, e.g. `grants[3].ticket: 'x' does not match ...`.

> **Dates and the examples.** Example grants expire in Oct-Dec 2026. Run them with `--today 2026-10-08` (as the README and CI do) or they will start to fail as "expired" later.

## Everyday recipes

All of these are edits to `access.yml` in a merge request:

| I need to... | Do this |
|---|---|
| Onboard a person | add under `people:` (`team`, `status: active`) and add them to a group such as `payments-devs` |
| Offboard a person | set `status: offboarded`, then delete their grants and group memberships (AAC005 fails until you do) |
| Give someone prod access for a task | one grant: `{ subject: alice, role: deployer, team: payments, env: prod, ticket: SEC-123, expires: <date <= 90 days> }` |
| Emergency access | a role with `delete`/Kubernetes `admin` (e.g. `break-glass`), `ticket` and `expires` within 7 days (AAC004) |
| Extend access | change `expires` and the `ticket`; never leave expired lines (AAC006) |
| Add a team | add it to `teams:`, add people, groups and grants. Vault needs a KV v2 mount `kv-<team>` and Kubernetes namespaces `<team>-<env>` |
| Add a role | add under `roles:`; leave a system out if the role gives nothing there |

## Conventions the tool relies on

* **Names** (`teams`, `environments`, roles, people, groups) are lowercase letters, digits and dashes.
* **Person id = login in the target systems.** It becomes the `User` name in Kubernetes RoleBindings (your OIDC username), the member in Vault identity groups and the key in GitLab `members.json`. If your IdP uses `a.smith`, rename or map it in your apply step.
* **Naming convention for targets:** Vault policy/group `<team>-<env>-<role>`, KV path `kv-<team>/data|metadata/<env>/*`, Kubernetes namespace `<team>-<env>`, RoleBinding `aac-<level>` bound to the built-in ClusterRole `view`/`edit`/`admin`.
* **AAC007 matches role names** `deployer` and `approver`. If you call them differently, the rule will not fire (see `SOD_ROLES` in `src/access_as_code/lint.py`).
* A group grant gives every member the role; two grants to the same person in the same place merge (the highest GitLab/Kubernetes level wins, Vault gets one policy per role).

## The model

```yaml
roles:
  developer: { vault: [read, list], kubernetes: edit, gitlab: developer }
  deployer:  { vault: [read, list, create, update], kubernetes: edit, gitlab: maintainer }
  approver:  { gitlab: maintainer }
people:
  alice: { team: payments, status: active }
groups:
  payments-devs: [alice, bob]
grants:
  - { subject: "group:payments-devs", role: developer, team: payments, env: dev }
  - { subject: alice, role: deployer, team: payments, env: prod, ticket: SEC-110, expires: 2026-12-15 }
```

One grant = *subject* + *role* + *team* + *environment* (+ ticket, expiry, reason). A role is a bundle of facets for each system, so "developer" means the same thing in Vault, Kubernetes and GitLab.

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

`lint` exits 1 on errors (`--strict`: also on warnings), so it works as a required merge-request check. `--today` pins the date for reproducible runs.

## Walkthrough on the bundled synthetic data

```text
$ access-as-code lint examples/access.bad.yml --today 2026-10-08
AAC001 error: role 'super-ops' grants the Vault 'sudo' capability
AAC003 error: grant #3 (bob -> deployer on payments/prod): direct production grant without an expiry
AAC005 error: grant #0 (group:payments-devs -> developer on payments/dev): 'gone' is offboarded
AAC007 error: 'alice' is both deployer and approver on payments/prod
...
11 error(s), 5 warning(s), 3 info                                   (exit 1)

$ access-as-code lint examples/access.yml --today 2026-10-08
AAC011 warning: grant #10 (bob -> break-glass on payments/prod): expires on 2026-10-12
0 error(s), 1 warning(s), 1 info                                    (exit 0)

$ access-as-code compile examples/access.yml --today 2026-10-08 --out build
wrote 20 files to build
```

Generated, for example `build/vault/policies/payments-prod-deployer.hcl`:

```hcl
path "kv-payments/data/prod/*" {
  capabilities = ["create", "read", "update"]
}

path "kv-payments/metadata/prod/*" {
  capabilities = ["list", "read"]
}
```

plus `vault/groups.json` (identity group -> policy + members), one Kubernetes `RoleBinding` per namespace and level (`payments-dev` / `edit`) and `gitlab/members.json` (highest level per person per team).

**Compile emits effective access only**: expired grants, offboarded people and invalid grants never reach the output, even if lint was skipped.

### Drift

```text
$ access-as-code diff examples/access.yml --today 2026-10-08 --actual actual.json
extra    vault_policies:legacy-admin  configured but not declared
changed  vault_policies:payments-dev-developer  content differs
changed  vault_groups:payments-dev-developer  missing members ['alice']
changed  vault_groups:payments-prod-break-glass  extra members ['zed']
missing  kubernetes:payments-dev/edit  declared but not configured
changed  gitlab:scoring  erin: declared 'developer', actual 'maintainer'
6 difference(s)                                                      (exit 1)
```

### Exporting the actual state from live systems

```bash
export VAULT_ADDR=https://vault.example.com VAULT_TOKEN=...      # needs list/read on sys/policies/acl and identity/*
export GITLAB_URL=https://gitlab.example.com GITLAB_TOKEN=...     # read_api scope, member of the team groups
access-as-code export-state access.yml --vault --kubernetes --gitlab --out snapshot.json
access-as-code diff access.yml --actual snapshot.json
```

* **Read-only**: only GET/LIST requests and `kubectl get`. Tokens are read from the environment and never written to the snapshot. Use a dedicated read-only token.
* **Vault**: all ACL policies except `default`/`root`, and all identity groups with their entity *names* (entity name must equal the person id). `VAULT_CACERT` is honoured.
* **Kubernetes**: `kubectl` with your current context. By default only RoleBindings labelled `managed-by=access-as-code` (what `compile` generates) are read; add `--k8s-all` to also catch hand-made RoleBindings to `view`/`edit`/`admin`.
* **GitLab**: *direct* members of the group `<prefix><team>` (`--gitlab-group-prefix 'acme/'`); guest/owner levels are exported as is, so an owner shows up as drift. A team without a group is reported as missing.
* * Safety: HTTPS is required (plain `http://` only for localhost), redirects are never followed, `VAULT_NAMESPACE` is honoured. A group member whose Vault entity was deleted appears as `<unknown-entity:id>`; Kubernetes Group/ServiceAccount subjects appear as `group:<name>` / `serviceaccount:<ns>:<name>` so over-privilege shows up as extra members; GitLab inherited (parent-group) members are not listed.
* A missing GitLab group is an error (wrong prefix or token?) unless `--gitlab-missing-ok`.
* Pass only the systems you can reach: the others are listed as `not checked`, not as drift.

This is covered by tests against a fake Vault/GitLab and a fake `kubectl`, **not against real instances**.

To reproduce the sample output without any live system: `access-as-code demo-state examples/access.yml --today 2026-10-08 --out actual.json` fabricates plausible hand-made changes. In real use you export the same four sections from your systems on a schedule and fail the job on any difference. Easiest way to learn the format: `compile` writes the "desired" side, and `demo-state` writes a complete example snapshot. Shape of the snapshot:

```json
{
  "vault_policies": { "payments-dev-developer": "<HCL text, as in build/vault/policies/*.hcl>" },
  "vault_groups":   { "payments-dev-developer": ["alice", "bob"] },
  "kubernetes":     { "payments-dev/edit": ["alice", "bob"] },
  "gitlab":         { "payments": { "alice": "maintainer" } }
}
```

A snapshot with none of the four sections is rejected (exit 2). A section that is absent from the snapshot is not checked; an empty one (`{}`) means "nothing configured" and reports everything declared as missing.

## Suggested workflow

1. `access.yml` lives in a repo with CODEOWNERS (security + team leads).
2. Merge request: CI runs `lint` (blocking) and shows `review`.
3. After merge: `compile`, apply with your tooling (Terraform Vault provider, `kubectl apply`, GitLab API).
4. Nightly: `export-state` then `diff`; page on drift.

## FAQ

* **`error: ... is a required property`** - the file failed the schema; `access-as-code validate` prints every problem with its path.
* **Lint passes locally but fails in CI** - dates: pin both with `--today`, or fix the grant that is about to expire (AAC011 warns 14 days ahead).
* **Does `compile` change my systems?** No. It only writes files; applying them (Terraform, `kubectl apply`, GitLab API) is your step.
* **Can I skip a rule for one grant?** No, by design. Change the rule in code via a reviewed PR or fix the grant.

## What is verified

Reproduce with `pip install -e ".[dev]" && pytest` (62 tests): every lint rule (positive, negative and boundary cases such as an expiry exactly 90 days away or a grant expiring today), schema rejection, group resolution, deterministic compilation, exclusion of expired/offboarded access, drift of every kind, CLI exit codes.

**Not verified:** applying the output to real Vault, Kubernetes or GitLab instances; the HCL, RoleBinding and member-level formats follow the public documentation but were never loaded into those systems. `export-state` was tested against fakes only; objects Vault returns for namespaces other than the token's, nested GitLab subgroups and inherited memberships are not exported. Vault policy paths assume KV v2 mounts named `kv-<team>`. Roles are per-team and per-environment; finer scoping (single paths, time-of-day) is out of scope.
