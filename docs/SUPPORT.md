# Support cheat sheet

[English](SUPPORT.md) | [Русский](SUPPORT.ru.md)

You do not need to know Vault, Kubernetes or GitLab. Your job: turn a ticket into a small edit of one YAML file, open a merge request, and read what the automatic check says.

## The 5-minute routine

1. Find the **team** of the resource in the ticket and open the file of its direction (`access/web.yml`, `access/infr.yml`, ...). Search for the team name.
2. Make **one** of the edits below. Write the ticket number in `ticket:`.
3. Check locally if you can: `access-as-code lint access` (nothing to install? skip, CI runs it for you).
4. Open a merge request titled with the ticket. CI checks it; the file owners review it. After the merge the automation applies it.

Useful questions before you edit: `access-as-code who access alice` ("what does Alice have today?") and `access-as-code matrix access` (overview per team).

## Recipes

Indentation is spaces, never tabs. Names are lowercase (`alice`, `sys-adm`). A date is `YYYY-MM-DD`.

### 1. New employee joins a team
Add the login to `members` (it must equal their login in Kubernetes/Vault/GitLab). They get the team's standard access automatically.
```yaml
    members: [alice, bob, newbie]      # <- add the name
```

### 2. Employee leaves the company
Move the name from `members` to `left`, and delete every line that mentions them under `extra` (in **all** files: `grep -rn name access/`).
```yaml
    members: [alice, bob]
    left: [newbie]
```
If you forget a line, CI fails with `AAC005 ... 'newbie' is offboarded`. Cannot be merged until fixed.

### 3. Temporary access to production (release, investigation)
Add a line under `extra`. Production needs `ticket` and `expires` (not further than 90 days).
```yaml
    extra:
      - { who: alice, role: deployer, env: prod, ticket: SEC-210, expires: 2026-11-30 }
```
Several people with the same access: `who: [alice, bob]`.

### 4. Emergency access ("break glass")
Only with an incident ticket, at most 7 days, and say why:
```yaml
      - { who: erin, role: break-glass, env: prod, ticket: SEC-220, expires: 2026-10-12, reason: "incident INC-77" }
```

### 5. Someone from another team needs access
Write the entry in the file/team that **owns the resource** (not the person's team). A ticket is required, otherwise CI warns `AAC008`.
```yaml
  devops:
    extra:
      - { who: alice, role: viewer, env: stage, ticket: SEC-230 }
```

### 6. Extend or remove access
Extend: change `expires` (and the ticket, if it is a new request). Remove: delete the line. Expired lines must be deleted, CI fails with `AAC006` otherwise; a warning `AAC011` appears 14 days before the date.

### 7. Change what the whole team gets
Edit the `access:` block of the team. This affects everyone in the team, so reviewers will look closely.
```yaml
    access:
      dev: developer
      stage: developer
      prod: { role: viewer, ticket: SEC-101 }
```

### 8. New team
Copy a team block under `teams:` in the file of its direction and rename it. Ask the platform team first to create the Vault mount `kv-<team>` and the Kubernetes namespaces `<team>-dev|stage|prod`.

## Roles in plain words

| Role | Can |
|---|---|
| `viewer` | read only |
| `developer` | work in the environment: read secrets, edit workloads, push code |
| `deployer` | everything `developer` does plus write secrets and release |
| `approver` | approves production releases (cannot be the same person as `deployer`, AAC007) |
| `break-glass` | emergency, can delete; 7 days maximum |

Unsure which role? Ask the ticket author what they must *do*, then pick the smallest role. The full list is in `access/common.yml`.

## Reading CI errors

`access-as-code explain AAC003` shows the full explanation for any code. The usual ones:

| Message | What to do |
|---|---|
| `AAC003 ... production grant without a ticket` | add `ticket: SEC-123` |
| `AAC003 ... direct production grant without an expiry` / `more than 90 days away` | add or shorten `expires:` |
| `AAC004 ... elevated role ... needs a ticket and an expiry within 7 days` | shorten `expires:` for `break-glass` |
| `AAC005 ... is offboarded` | recipe 2: remove the leftover lines |
| `AAC006 ... expired on ...` | delete the line |
| `AAC007 ... both deployer and approver` | give the two roles to different people |
| `AAC002 ... unknown ...` | typo in a name, or the person/team is not declared |
| `web.yml: teams.sites.extra[1]: 'env' is a required property` | a field is missing in the 2nd `extra` line of team `sites` in `web.yml` |
| `person 'x' is defined in web.yml and again in infr.yml` | the same login is in two teams; keep one |

Anything unclear: do not guess, ask in the merge request. Nothing you push changes real access until it is reviewed and merged.
