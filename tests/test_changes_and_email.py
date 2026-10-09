from __future__ import annotations

import json
import shutil
from datetime import date

import pytest

from access_as_code.changes import compare
from access_as_code.cli import main
from access_as_code.compile import compile_access
from access_as_code.lint import lint
from access_as_code.model import load, parse
from conftest import BASE, ROOT, TODAY
from test_layout import COMMON, problems, write

COMPANY = ROOT / "examples" / "company"
DAY = date(2026, 10, 8)


def copy_catalog(tmp_path, name):
    dst = tmp_path / name
    shutil.copytree(COMPANY, dst)
    return dst


def edit(path, filename, old, new):
    f = path / filename
    text = f.read_text()
    assert old in text
    f.write_text(text.replace(old, new, 1))


# ---- who gained or lost access ----


def test_no_changes_between_identical_catalogs(tmp_path):
    report = compare(load(str(COMPANY)), load(str(COMPANY)), DAY)
    assert report.changes == [] and report.new_accounts == [] and report.gone_accounts == []


def test_gained_lost_changed_and_accounts(tmp_path):
    base, head = copy_catalog(tmp_path, "base"), copy_catalog(tmp_path, "head")
    edit(
        head,
        "web.yml",
        "{ who: carol, role: viewer,   env: stage, ticket: SEC-130 }",
        "{ who: carol, role: developer, env: stage, ticket: SEC-130 }",
    )
    edit(head, "web.yml", "ticket: SEC-110, expires: 2026-12-15", "ticket: SEC-110, expires: 2027-01-05")
    edit(
        head,
        "web.yml",
        "      bob: bob@corp.example\n",
        "      bob: bob@corp.example\n      newbie: newbie@corp.example\n",
    )
    edit(
        head,
        "infr.yml",
        "      - { who: frank, role: deployer,    env: prod, ticket: SEC-114, expires: 2026-12-01 }\n",
        "",
    )
    report = compare(load(str(base)), load(str(head)), DAY)
    kinds = {(c.kind, c.key) for c in report.changes}
    assert ("gained", ("carol", "sites", "stage", "developer")) in kinds
    assert ("lost", ("carol", "sites", "stage", "viewer")) in kinds
    assert ("lost", ("frank", "devops", "prod", "deployer")) in kinds
    assert ("changed", ("alice", "sites", "prod", "deployer")) in kinds
    assert report.new_accounts == ["newbie"]
    assert report.gone_accounts == []  # frank still has team access


def test_leaving_removes_the_account(tmp_path):
    base, head = copy_catalog(tmp_path, "base"), copy_catalog(tmp_path, "head")
    edit(head, "web.yml", "      bob: bob@corp.example\n", "")
    edit(head, "web.yml", "    left: [ivan]", "    left: [ivan]")
    edit(
        head,
        "web.yml",
        "      - { who: bob,   role: approver, env: prod, ticket: SEC-111, expires: 2026-12-15 }\n",
        "",
    )
    report = compare(load(str(base)), load(str(head)), DAY)
    assert report.gone_accounts == ["bob"]
    assert all(c.kind == "lost" for c in report.changes if c.person == "bob")


def test_missing_base_means_everything_is_new(tmp_path, capsys):
    args = [str(tmp_path / "nope"), str(COMPANY), "--today", "2026-10-08"]
    assert main(["changes", *args]) == 2  # a typo in the base path must not look like a new catalog
    assert main(["changes", *args, "--base-may-be-missing"]) == 0
    out = capsys.readouterr().out
    assert "New accounts to create: alice, bob" in out and "0 lost" in out


def test_changes_formats(tmp_path, capsys):
    head = copy_catalog(tmp_path, "head")
    edit(
        head,
        "web.yml",
        "      bob: bob@corp.example\n",
        "      bob: bob@corp.example\n      newbie: newbie@corp.example\n",
    )
    args = [str(COMPANY), str(head), "--today", "2026-10-08"]
    assert main(["changes", *args, "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["new_accounts"] == ["newbie"] and {c["person"] for c in data["changes"]} == {"newbie"}
    assert data["changes"][0]["new"] == {"via": ["group:sites-team"], "tickets": [], "expires": None}
    assert main(["changes", *args, "--format", "markdown"]) == 0
    out = capsys.readouterr().out
    assert "| ➕ gained | `newbie` |" in out and "**New accounts to create:** newbie" in out
    assert main(["changes", str(COMPANY), str(COMPANY), "--today", "2026-10-08"]) == 0
    assert "No change" in capsys.readouterr().out


# ---- corporate email ----


def with_people(doc, **emails):
    for pid, email in emails.items():
        doc["people"][pid]["email"] = email
    return doc


def rules(doc):
    return [(v.rule, v.message) for v in lint(parse(doc), TODAY)]


def test_email_is_optional_by_default(doc):
    assert not [r for r, _ in rules(doc) if r in ("AAC012", "AAC013", "AAC014")]


def test_require_email_flags_active_people_only(doc):
    doc["require_email"] = True
    missing = [m for r, m in rules(doc) if r == "AAC012"]
    assert any("'alice'" in m for m in missing) and not any(
        "'gone'" in m for m in missing
    )  # gone is offboarded
    with_people(doc, alice="alice@corp.example", bob="bob@corp.example", zoe="zoe@corp.example")
    assert not [r for r, _ in rules(doc) if r == "AAC012"]


def test_shared_mailbox_is_an_error_and_the_address_stays_out_of_logs(doc):
    with_people(doc, alice="Team@corp.example", bob="team@CORP.example")
    shared = [m for r, m in rules(doc) if r == "AAC013"]
    assert len(shared) == 1 and "'alice'" in shared[0] and "'bob'" in shared[0]
    assert "corp.example" not in shared[0].lower()


def test_email_domain_allowlist(doc):
    doc["email_domains"] = ["corp.example"]
    with_people(doc, alice="alice@corp.example", bob="bob@gmail.com")
    found = [m for r, m in rules(doc) if r == "AAC014"]
    assert len(found) == 1 and "'bob'" in found[0] and "gmail.com" in found[0] and "bob@" not in found[0]


@pytest.mark.parametrize("bad", ["alice", "alice@", "a b@corp.example", "alice@corp", "x@y@corp.example"])
def test_malformed_email_is_rejected_by_the_schema(doc, bad):
    from access_as_code.errors import AccessFileError

    with_people(doc, alice=bad)
    with pytest.raises(AccessFileError):
        parse(doc)


def test_members_mapping_form_with_and_without_address(tmp_path):
    team = "version: 2\nteams:\n  sites:\n    members:\n      alice: alice@corp.example\n      bob:\n"
    acc = load(str(write(tmp_path, common=COMMON, web=team)))
    assert acc.people["alice"].email == "alice@corp.example"
    assert acc.people["bob"].email is None and acc.people["bob"].active


def test_settings_live_in_one_file_only(tmp_path):
    a = COMMON + "require_email: true\n"
    got = problems(write(tmp_path, common=a, other="version: 2\nrequire_email: false\n"))
    assert any("setting 'require_email' is defined in" in p for p in got)


def test_company_example_enforces_email_policy():
    acc = load(str(COMPANY))
    assert acc.require_email and acc.email_domains == ("corp.example",)
    assert all(p.email for p in acc.people.values() if p.active)


def test_people_json_lists_active_people_with_access_and_no_secrets(tmp_path):
    out = tmp_path / "b"
    assert main(["compile", str(COMPANY), "--today", "2026-10-08", "--out", str(out)]) == 0
    people = json.loads((out / "people.json").read_text())
    assert "ivan" not in people  # left the company
    alice = people["alice"]
    assert alice["email"] == "alice@corp.example" and alice["team"] == "sites"
    assert alice["systems"] == ["gitlab", "kubernetes", "vault"]
    assert "sites/prod:deployer" in alice["access"]
    assert set(alice) == {"email", "team", "systems", "access"}  # nothing credential-like


def test_people_json_only_has_people_with_effective_access(doc):
    doc["grants"] = [
        {"subject": "alice", "role": "viewer", "team": "payments", "env": "dev"},
        {"subject": "bob", "role": "viewer", "team": "payments", "env": "dev", "expires": "2020-01-01"},
    ]
    people = compile_access(parse(doc), TODAY).people
    assert set(people) == {"alice"} and people["alice"]["email"] is None


def test_drift_state_does_not_include_people(doc):
    assert "people" not in compile_access(parse(BASE | {"grants": []}), TODAY).as_state()


def test_offboarded_people_are_exempt_from_mailbox_rules(doc):
    doc["email_domains"] = ["corp.example"]
    with_people(
        doc, alice="a@corp.example", gone="a@gmail.com"
    )  # same box and a private domain, but offboarded
    assert not [r for r, _ in rules(doc) if r in ("AAC013", "AAC014")]


def test_accounts_only_count_roles_that_touch_a_system(doc):
    doc["roles"]["nothing"] = {}
    base = parse(doc | {"grants": []})
    head = parse(
        doc
        | {
            "grants": [
                {"subject": "alice", "role": "nothing", "team": "payments", "env": "dev"},
                {"subject": "bob", "role": "viewer", "team": "payments", "env": "dev"},
            ]
        }
    )
    assert compare(base, head, TODAY).new_accounts == ["bob"]


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    team = (
        "version: 2\nteams:\n  sites:\n    members:\n      alice: a@corp.example\n      alice: b@x.example\n"
    )
    assert any("duplicate key 'alice'" in p for p in problems(write(tmp_path, common=COMMON, web=team)))


def test_people_json_is_not_part_of_the_pr_diff_in_the_workflow():
    text = (ROOT / ".github" / "workflows" / "access-check.yml").read_text()
    assert "diff -ru -x people.json" in text
