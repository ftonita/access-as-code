"""One-paragraph fix instructions per lint rule, shown by `access-as-code explain`."""

from __future__ import annotations

HOWTO = {
    "AAC001": "Remove `sudo` from the role's `vault:` list. Needing sudo means the work belongs to the Vault admins, not to a role in this file.",
    "AAC002": "Fix the typo or declare the missing object: add the team/environment/role/person under its top-level key, or correct the name in the grant or group (a group member must be listed under people).",
    "AAC003": "Add `ticket: SEC-123` to the grant. For a grant to one person (not a group) also add `expires: YYYY-MM-DD`, at most 90 days from today.",
    "AAC004": "Break-glass style roles in production need `ticket:` and `expires:` within 7 days. Re-issue the grant each time instead of extending it.",
    "AAC005": "Delete the offboarded person's grants and remove them from every group (or ask HR/IdP owners to confirm the status).",
    "AAC006": "Delete the expired grant from `grants:`. Removing it from the file is what revokes the access.",
    "AAC007": "Give the two duties to two different people (a role named `deployer` and a role named `approver` on the same team in production). Check group memberships too.",
    "AAC008": "Add a `ticket:` explaining why a person from another team needs this access, or move the person to the right team.",
    "AAC009": "Delete the duplicate line; keep the one with the right ticket and expiry.",
    "AAC010": "Delete the unused role/group, or add the grant you forgot. Informational only.",
    "AAC011": "Decide before the date: remove the grant, or renew it with a new ticket and expiry. Warning only (use `lint --strict` to make it block).",
    "AAC012": "Add the person's corporate address: in a team use the mapping form `members: { alice: alice@corp.example }`. People without an address cannot receive their local-account credentials.",
    "AAC013": "Each person needs their own mailbox, because credentials are sent personally. Fix the typo, or remove the duplicate person.",
    "AAC014": "Use the person's corporate address (the domains are listed under `email_domains` in common.yml). Credentials must never go to a private mailbox.",
}
