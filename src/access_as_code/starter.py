"""Templates written by `access-as-code init`. They lint clean as-is; replace the sample names with your own."""

SCHEMA_URL = "https://raw.githubusercontent.com/ftonita/access-as-code/main/schema/access.v2.schema.json"

_SCHEMA_LINE = f"# yaml-language-server: $schema={SCHEMA_URL}\n"

_COMMON_BODY = """\
environments: [dev, stage, prod]
production_environments: [prod]   # stricter rules apply here: ticket, expiry, separation of duties

require_email: true               # every active person needs a corporate address (credentials are sent there)
email_domains: [corp.example]     # replace with your corporate domain(s); private mailboxes are rejected

roles:                            # a role = what it means in Vault / Kubernetes / GitLab
  viewer:    { description: read-only,          vault: [read, list], kubernetes: view, gitlab: reporter }
  developer: { description: daily development,  vault: [read, list], kubernetes: edit, gitlab: developer }
  deployer:  { description: ships releases,     vault: [read, list, create, update], kubernetes: edit, gitlab: maintainer }
  approver:  { description: approves releases,  gitlab: maintainer }
"""

_TEAM_BODY = """\
teams:
  myteam:
    members:                       # login: corporate email (the login = their login in Kubernetes/Vault/GitLab)
      alice: alice@corp.example
      bob: bob@corp.example
    access:                        # what EVERY member gets, per environment
      dev: developer
      stage: developer
      prod: { role: viewer, ticket: SEC-1 }      # production always needs a ticket
    extra:                         # one-off or temporary access (production: ticket + expiry, max 90 days)
      - { who: alice, role: deployer, env: prod, ticket: SEC-2, expires: @EXPIRES@ }
      - { who: bob,   role: approver, env: prod, ticket: SEC-3, expires: @EXPIRES@ }
"""


def starter_files(single: bool, expires: str) -> dict[str, str]:
    """name -> content. `single`: everything in one file (the caller ignores the name)."""
    common_note = "# Shared by all directions: environments and roles. Changed rarely. Owner: security.\n"
    team_note = (
        "# One file per direction (web, infr, ...). Rename the team and the people, add more teams below.\n"
    )
    files = {
        "common.yml": f"{_SCHEMA_LINE}{common_note}version: 2\n\n{_COMMON_BODY}",
        "myteam.yml": f"{_SCHEMA_LINE}{team_note}version: 2\n\n{_TEAM_BODY}",
        "access.yml": f"{_SCHEMA_LINE}# Everything in one file; split it per direction when it grows.\nversion: 2\n\n"
        f"{_COMMON_BODY}\n{_TEAM_BODY}",
    }
    names = ["access.yml"] if single else ["common.yml", "myteam.yml"]
    return {n: files[n].replace("@EXPIRES@", expires) for n in names}
