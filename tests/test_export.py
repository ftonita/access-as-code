from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from access_as_code.cli import main
from access_as_code.drift import diff, unchecked
from access_as_code.export import ExportError, export_gitlab, export_kubernetes, export_state, export_vault
from conftest import GOOD

ROUTES = {
    "/v1/sys/policies/acl": {"data": {"keys": ["default", "root", "p1"]}},
    "/v1/sys/policies/acl/p1": {"data": {"policy": 'path "x" {}\n'}},
    "/v1/identity/group/name": {"data": {"keys": ["g1"]}},
    "/v1/identity/group/name/g1": {"data": {"member_entity_ids": ["e2", "e1"], "policies": ["p1"]}},
    "/v1/identity/entity/id/e1": {"data": {"name": "alice"}},
    "/v1/identity/entity/id/e2": {"data": {"name": "bob"}},
    "/api/v4/groups/payments/members": [
        {"username": "alice", "access_level": 40},
        {"username": "bob", "access_level": 30},
    ],
}
SEEN: list[tuple[str, str]] = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        SEEN.append(
            (self.command, self.headers.get("X-Vault-Token") or self.headers.get("PRIVATE-TOKEN") or "")
        )
        if path in ROUTES:
            body = json.dumps(ROUTES[path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            if path.endswith("/members"):
                self.send_header("X-Next-Page", "")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/v1/sys/policies/acl/redir":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/x")
            self.end_headers()
        elif path == "/v1/sys/policies/acl/forbidden":
            self.send_response(403)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    SEEN.clear()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_export_vault(server):
    policies, groups = export_vault(server, "tok")
    assert policies == {"p1": 'path "x" {}\n'}  # default/root are ignored
    assert groups == {"g1": ["alice", "bob"]}
    assert {m for m, _ in SEEN} == {"GET"}  # read-only
    assert {t for _, t in SEEN} == {"tok"}


def test_export_vault_error_mentions_status_not_token(server):
    ROUTES["/v1/sys/policies/acl"]["data"]["keys"].append("forbidden")
    try:
        with pytest.raises(ExportError, match="HTTP 403") as exc:
            export_vault(server, "secret-token")
        assert "secret-token" not in str(exc.value)
    finally:
        ROUTES["/v1/sys/policies/acl"]["data"]["keys"].remove("forbidden")


def test_export_gitlab_maps_levels_and_skips_missing_group(server):
    got = export_gitlab(server, "t", ["payments", "scoring"], missing_ok=True)
    assert got == {"payments": {"alice": "maintainer", "bob": "developer"}}


def test_export_kubernetes_filters_and_unions():
    items = {
        "items": [
            {
                "metadata": {"namespace": "a-dev"},
                "roleRef": {"kind": "ClusterRole", "name": "edit"},
                "subjects": [{"kind": "User", "name": "bob"}, {"kind": "Group", "name": "g"}],
            },
            {
                "metadata": {"namespace": "a-dev"},
                "roleRef": {"kind": "ClusterRole", "name": "edit"},
                "subjects": [{"kind": "User", "name": "alice"}],
            },
            {"metadata": {"namespace": "a-dev"}, "roleRef": {"kind": "Role", "name": "edit"}, "subjects": []},
            {"metadata": {"namespace": "a-dev"}, "roleRef": {"kind": "ClusterRole", "name": "cluster-admin"}},
        ]
    }
    calls = []

    def kubectl(args):
        calls.append(args)
        return json.dumps(items)

    assert export_kubernetes(kubectl) == {"a-dev/edit": ["alice", "bob", "group:g"]}
    assert "-l" in calls[0]
    export_kubernetes(kubectl, all_bindings=True)
    assert "-l" not in calls[1]


def test_url_must_be_https_except_localhost():
    for bad in ("file:///etc/passwd", "http://vault.example.com"):
        with pytest.raises(ExportError, match="https"):
            export_vault(bad, "t")


def test_redirects_are_not_followed(server):
    ROUTES["/v1/sys/policies/acl"]["data"]["keys"].append("redir")
    try:
        with pytest.raises(ExportError):
            export_vault(server, "t")
    finally:
        ROUTES["/v1/sys/policies/acl"]["data"]["keys"].remove("redir")


def test_gitlab_missing_group_is_an_error_unless_allowed(server):
    with pytest.raises(ExportError, match="not found"):
        export_gitlab(server, "t", ["scoring"])
    assert export_gitlab(server, "t", ["scoring"], missing_ok=True) == {}


def test_kubernetes_other_subject_kinds_surface():
    doc = {
        "items": [
            {
                "metadata": {"namespace": "n"},
                "roleRef": {"kind": "ClusterRole", "name": "admin"},
                "subjects": [
                    {"kind": "Group", "name": "ops"},
                    {"kind": "ServiceAccount", "name": "ci", "namespace": "tools"},
                ],
            }
        ]
    }
    assert export_kubernetes(lambda a: json.dumps(doc), all_bindings=True) == {
        "n/admin": ["group:ops", "serviceaccount:tools:ci"]
    }


def test_diff_rejects_snapshot_without_known_sections(tmp_path):
    bad = tmp_path / "s.json"
    bad.write_text("{}")
    assert main(["diff", str(GOOD), "--today", "2026-10-08", "--actual", str(bad)]) == 2


def test_partial_snapshot_is_not_compared():
    desired = {"vault_policies": {"a": "x"}, "gitlab": {"t": {"u": "developer"}}}
    actual = {"gitlab": {"t": {"u": "developer"}}}
    assert diff(desired, actual) == []
    assert "vault_policies" in unchecked(actual)
    assert [d.kind for d in diff(desired, {**actual, "vault_policies": {}})] == ["missing"]


def test_cli_export_state_roundtrip(server, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_ADDR", server)
    monkeypatch.setenv("VAULT_TOKEN", "tok")
    out = tmp_path / "s.json"
    assert main(["export-state", str(GOOD), "--vault", "--out", str(out)]) == 0
    state = json.loads(out.read_text())
    assert set(state) == {"vault_policies", "vault_groups"}
    assert "tok" not in out.read_text()
    assert main(["diff", str(GOOD), "--today", "2026-10-08", "--actual", str(out)]) == 1
    assert "not checked" in capsys.readouterr().out


def test_cli_export_state_input_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    assert main(["export-state", str(GOOD), "--out", str(tmp_path / "s.json")]) == 2  # nothing selected
    assert main(["export-state", str(GOOD), "--vault", "--out", str(tmp_path / "s.json")]) == 2  # no env


def test_export_state_composes_systems(server):
    state = export_state(["payments"], vault=(server, "t"), gitlab=(server, "t"))
    assert set(state) == {"vault_policies", "vault_groups", "gitlab"}
