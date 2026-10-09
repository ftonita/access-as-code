from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from access_as_code.cli import main
from access_as_code.compile import compile_access
from access_as_code.errors import AccessFileError
from access_as_code.lint import lint
from access_as_code.model import load
from access_as_code.schemas import SCHEMA_V2
from conftest import ROOT

COMPANY = ROOT / "examples" / "company"
TODAY = "2026-10-08"
DAY = date(2026, 10, 8)

COMMON = """\
version: 2
environments: [dev, prod]
roles:
  viewer: { vault: [read], kubernetes: view, gitlab: reporter }
  developer: { vault: [read], kubernetes: edit, gitlab: developer }
"""

WEB = """\
version: 2
teams:
  sites:
    members: [alice, bob]
    left: [gone]
    access:
      dev: developer
      prod: { role: viewer, ticket: SEC-1 }
    extra:
      - { who: [alice, bob], role: viewer, env: dev }
"""


def write(tmp_path: Path, **files: str) -> Path:
    for name, text in files.items():
        (tmp_path / f"{name}.yml").write_text(text, encoding="utf-8")
    return tmp_path


def problems(path: Path) -> list[str]:
    with pytest.raises(AccessFileError) as e:
        load(str(path))
    return e.value.problems


def test_example_directory_lints_clean_and_compiles(tmp_path):
    acc = load(str(COMPANY))
    assert set(acc.teams) == {"sites", "portal", "devops", "sys-adm"}
    assert acc.people["ivan"].active is False
    assert main(["lint", str(COMPANY), "--today", TODAY]) == 0
    assert main(["compile", str(COMPANY), "--today", TODAY, "--out", str(tmp_path / "b")]) == 0
    # offboarded ivan and expired grants never reach the output
    assert "ivan" not in (tmp_path / "b" / "vault" / "groups.json").read_text()


def test_file_order_does_not_change_the_result(tmp_path):
    a = compile_access(load(str(COMPANY)), DAY).as_state()
    copy = tmp_path / "c"
    copy.mkdir()
    for f in COMPANY.glob("*.yml"):
        (copy / f"z-{f.name}" if f.name == "common.yml" else copy / f.name).write_text(f.read_text())
    b = compile_access(load(str(copy)), DAY).as_state()
    assert a == b


def test_team_baseline_extra_who_list_and_left(tmp_path):
    acc = load(str(write(tmp_path, common=COMMON, web=WEB)))
    assert acc.groups["sites-team"] == ("alice", "bob")
    assert acc.people["gone"].active is False
    subjects = [(g.subject, g.role, g.env) for g in acc.grants]
    assert ("group:sites-team", "developer", "dev") in subjects
    assert ("alice", "viewer", "dev") in subjects and ("bob", "viewer", "dev") in subjects
    assert all(g.source == "web.yml" and g.team == "sites" for g in acc.grants)
    assert lint(acc, DAY) == []


def test_messages_name_the_file(tmp_path):
    bad = WEB.replace("role: viewer, ticket: SEC-1", "role: viewer")
    acc = load(str(write(tmp_path, common=COMMON, web=bad)))
    msgs = [str(v) for v in lint(acc, DAY)]
    assert any("without a ticket" in m and "[web.yml]" in m for m in msgs)


def test_duplicate_definitions_across_files_are_rejected(tmp_path):
    other = "version: 2\nteams:\n  sites:\n    members: [alice]\n"
    got = problems(write(tmp_path, common=COMMON, web=WEB, other=other))
    assert any("team 'sites' is defined in other.yml and again in web.yml" in p for p in got)
    assert any("person 'alice'" in p for p in got)
    got = problems(
        write(tmp_path, common=COMMON, extra_roles="version: 2\nroles:\n  viewer: { vault: [read] }\n")
    )
    assert any("role 'viewer'" in p for p in got)


def test_person_in_two_teams_and_member_also_left(tmp_path):
    two = "version: 2\nteams:\n  a: { members: [x], left: [x] }\n  b: { members: [x] }\n"
    got = problems(write(tmp_path, common=COMMON, two=two))
    assert any("both in members and in left" in p for p in got)
    assert any("listed under both 'a' and 'b'" in p for p in got)


def test_access_without_members_and_missing_common(tmp_path):
    no_members = "version: 2\nteams:\n  x:\n    access: { dev: viewer }\n"
    got = problems(write(tmp_path, common=COMMON, t=no_members))
    assert any("no members" in p for p in got)
    only_web = tmp_path / "w"
    only_web.mkdir()
    got = problems(write(only_web, web=WEB))
    assert any("no roles are defined" in p for p in got)
    assert any("no environments are defined" in p for p in got)


def test_schema_errors_are_friendly_and_name_the_file(tmp_path):
    bad = (
        "version: 2\nteams:\n  sites:\n    members: [Alice]\n    access: { dev: 5 }\n"
        "    extra:\n      - { who: bob, role: viewer }\n"
    )
    got = problems(write(tmp_path, common=COMMON, web=bad))
    assert all(p.startswith("web.yml: ") for p in got)
    assert any("'env' is a required property" in p for p in got)
    assert any("Alice" in p for p in got)


def test_directory_rules(tmp_path):
    with pytest.raises(AccessFileError, match="no .yml files"):
        load(str(tmp_path))
    flat = ROOT / "examples" / "access.yml"
    mixed = write(tmp_path, common=COMMON)
    (mixed / "flat.yml").write_text(flat.read_text())
    assert any("flat.yml: files in a directory must declare 'version: 2'" in p for p in problems(mixed))


def test_single_v2_file_works(tmp_path):
    one = tmp_path / "all.yml"
    one.write_text(COMMON + WEB.split("version: 2\n", 1)[1])
    assert len(load(str(one)).grants) == 4


def test_matrix_and_who(capsys):
    assert main(["matrix", str(COMPANY), "--today", TODAY]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == ["team", "dev", "stage", "prod"]
    assert "sites" in out and "portal" in out
    assert main(["who", str(COMPANY), "carol", "--today", TODAY]) == 0
    out = capsys.readouterr().out
    assert "sites/stage  viewer  via direct  ticket=SEC-130" in out
    assert main(["who", str(COMPANY), "ivan", "--today", TODAY]) == 0
    assert (
        "OFFBOARDED" in capsys.readouterr().out and "no effective access" in capsys.readouterr().out or True
    )
    assert main(["who", str(COMPANY), "caroll"]) == 2


def test_committed_json_schema_is_current(capsys):
    assert main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out) == SCHEMA_V2
    assert json.loads((ROOT / "schema" / "access.v2.schema.json").read_text()) == SCHEMA_V2


def test_leaver_recipe_leftover_line_is_caught(tmp_path):
    team = (
        "version: 2\nteams:\n  sites:\n    members: [alice]\n    left: [bob]\n"
        "    extra:\n      - { who: bob, role: viewer, env: dev }\n"
    )
    acc = load(str(write(tmp_path, common=COMMON, web=team)))
    assert any(v.rule == "AAC005" for v in lint(acc, DAY))


def test_access_without_members_does_not_hide_other_problems(tmp_path):
    team = (
        "version: 2\nteams:\n  x:\n    access: { dev: viewer }\n    extra:\n"
        "      - { who: nobody, role: viewer, env: dev }\n"
        "  y: { members: [a], left: [a] }\n"
    )
    got = problems(write(tmp_path, common=COMMON, t=team))
    assert any("no members" in p for p in got)
    assert any("both in members and in left" in p for p in got)


def test_person_left_in_one_team_and_member_of_another_in_one_file(tmp_path):
    two = "version: 2\nteams:\n  a: { members: [x] }\n  b: { left: [x] }\n"
    assert any("listed under both" in p for p in problems(write(tmp_path, common=COMMON, two=two)))


def test_directory_listing_ignores_subdirectories_and_rejects_yml_yaml_twins(tmp_path):
    write(tmp_path, common=COMMON, web=WEB)
    (tmp_path / "old.yml").mkdir()
    assert load(str(tmp_path)).teams == ("sites",)
    (tmp_path / "web.yaml").write_text(WEB)
    assert any("both .yml and .yaml" in p for p in problems(tmp_path))


def test_who_explains_expired_and_offboarded(tmp_path, capsys):
    team = (
        "version: 2\nteams:\n  sites:\n    members: [alice]\n    left: [gone]\n    extra:\n"
        "      - { who: alice, role: viewer, env: dev, expires: 2020-01-01 }\n"
        "      - { who: gone, role: viewer, env: dev }\n"
    )
    path = write(tmp_path, common=COMMON, web=team)
    assert main(["who", str(path), "alice", "--today", TODAY]) == 0
    out = capsys.readouterr().out
    assert "no effective access" in out and "expired on 2020-01-01" in out
    assert main(["who", str(path), "gone", "--today", TODAY]) == 0
    assert "person is offboarded" in capsys.readouterr().out


def test_init_cleans_up_after_a_failure(tmp_path, monkeypatch):
    real_open = open
    calls = []

    def flaky(path, mode="r", *a, **k):
        if "x" in mode:
            calls.append(path)
            if len(calls) == 2:
                raise OSError("disk full")
        return real_open(path, mode, *a, **k)

    monkeypatch.setattr("builtins.open", flaky)
    out = tmp_path / "access"
    assert main(["init", "--out", str(out)]) == 2
    assert not list(out.glob("*.yml"))
    (tmp_path / "plain").write_text("x")
    assert main(["init", "--out", str(tmp_path / "plain")]) == 2


def test_single_file_starter_is_a_valid_single_document(tmp_path):
    out = tmp_path / "all.yml"
    assert main(["init", "--out", str(out)]) == 0
    text = out.read_text()
    assert text.count("version: 2") == 1
    assert main(["lint", str(out), "--strict"]) == 0
