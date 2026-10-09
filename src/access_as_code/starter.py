"""Template written by `access-as-code init`. Lints clean as-is; replace the sample names with your own."""

STARTER = """\
# access.yml - the single source of truth for who may do what.
# Every change to this file goes through a merge request. See README for the walkthrough.
version: 1

teams: [myteam]                   # lowercase letters, digits, dashes
environments: [dev, stage, prod]
production_environments: [prod]   # stricter rules apply here (ticket, expiry, separation of duties)

# A role is a bundle of rights per system. Leave a system out if the role has no access there.
roles:
  viewer:    { description: read-only,          vault: [read, list], kubernetes: view, gitlab: reporter }
  developer: { description: daily development,  vault: [read, list], kubernetes: edit, gitlab: developer }
  deployer:  { description: ships releases,     vault: [read, list, create, update], kubernetes: edit, gitlab: maintainer }
  approver:  { description: approves releases,  gitlab: maintainer }   # never give deployer + approver to one person

# `id` must equal the login used in Kubernetes (OIDC username) and the Vault entity name.
people:
  alice: { team: myteam, status: active }
  bob:   { team: myteam, status: active }

groups:
  myteam-devs: [alice, bob]

grants:
  # whole group, non-production: no ticket needed
  - { subject: "group:myteam-devs", role: developer, team: myteam, env: dev }
  - { subject: "group:myteam-devs", role: developer, team: myteam, env: stage }
  # production always needs a ticket
  - { subject: "group:myteam-devs", role: viewer, team: myteam, env: prod, ticket: SEC-1 }
  # one person in production: ticket AND expiry (max 90 days ahead; init uses today + 30)
  - { subject: alice, role: deployer, team: myteam, env: prod, ticket: SEC-2, expires: @EXPIRES@ }
"""
