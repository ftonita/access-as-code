"""Export the *actual* state from live Vault, Kubernetes and GitLab, in the shape `diff` expects.

Read-only: only GET/LIST requests and `kubectl get`. Credentials come from the environment
(VAULT_ADDR/VAULT_TOKEN, GITLAB_URL/GITLAB_TOKEN, kubeconfig) and are never written to the output.
Standard library only; HTTP and kubectl are injectable so tests need no network.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

# (url, headers, method) -> (parsed JSON body, response headers). Raises ExportError (404 -> NotFound).
Fetch = Callable[[str, dict[str, str], str], tuple[Any, dict[str, str]]]
Kubectl = Callable[[list[str]], str]

VAULT_BUILTIN_POLICIES = {"default", "root"}
GITLAB_LEVELS = {5: "minimal", 10: "guest", 20: "reporter", 30: "developer", 40: "maintainer", 50: "owner"}
K8S_LEVELS = ("view", "edit", "admin")


class ExportError(ValueError):
    """Cannot read the live system (network, auth, unexpected response)."""


class NotFound(ExportError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: they would forward the token header to another host."""

    def redirect_request(self, *args, **kwargs):
        return None


def http_fetch(url: str, headers: dict[str, str], method: str = "GET") -> tuple[Any, dict[str, str]]:
    ca = os.environ.get("VAULT_CACERT") or os.environ.get("SSL_CERT_FILE")
    ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx))
        with opener.open(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return (json.loads(body) if body else {}), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound(f"{method} {url}: 404") from exc
        raise ExportError(f"{method} {url}: HTTP {exc.code} (check the token and its policy)") from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"{method} {url}: {exc}") from exc


def run_kubectl(args: list[str]) -> str:
    try:
        done = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603, S607
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExportError(f"kubectl failed: {exc}") from exc
    if done.returncode != 0:
        raise ExportError(f"kubectl {' '.join(args)}: {done.stderr.strip() or done.returncode}")
    return done.stdout


def _base(url: str, what: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" and not (
        parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1")
    ):
        raise ExportError(f"{what} must be an https:// URL (http:// only for localhost), got {url!r}")
    return url.rstrip("/")


def export_vault(
    addr: str, token: str, fetch: Fetch = http_fetch
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """-> (policies {name: hcl}, identity groups {name: sorted entity names})."""
    base = _base(addr, "VAULT_ADDR")
    hdr = {"X-Vault-Token": token}
    if os.environ.get("VAULT_NAMESPACE"):
        hdr["X-Vault-Namespace"] = os.environ["VAULT_NAMESPACE"]

    def get(path: str, method: str = "GET") -> Any:
        return fetch(f"{base}/v1/{path}", hdr, method)[0]

    names = get("sys/policies/acl?list=true", "GET").get("data", {}).get("keys", [])
    policies = {}
    for name in sorted(set(names) - VAULT_BUILTIN_POLICIES):
        policies[name] = get(f"sys/policies/acl/{urllib.parse.quote(name, safe='')}")["data"]["policy"]

    try:
        group_names = get("identity/group/name?list=true").get("data", {}).get("keys", [])
    except NotFound:  # Vault answers 404 for an empty list
        group_names = []
    entity_names: dict[str, str] = {}
    groups: dict[str, list[str]] = {}
    for name in sorted(group_names):
        data = get(f"identity/group/name/{urllib.parse.quote(name, safe='')}")["data"]
        members = []
        for eid in data.get("member_entity_ids") or []:
            if eid not in entity_names:
                try:
                    entity_names[eid] = get(f"identity/entity/id/{eid}")["data"]["name"]
                except NotFound:
                    entity_names[eid] = f"<unknown-entity:{eid}>"
            members.append(entity_names[eid])
        groups[name] = sorted(members)
    return policies, groups


def _subject(s: dict[str, Any], namespace: str) -> str:
    """User -> its name (what `compile` writes); other kinds are prefixed so they surface as extra members."""
    kind = s.get("kind")
    if kind == "User":
        return s["name"]
    if kind == "ServiceAccount":
        return f"serviceaccount:{s.get('namespace', namespace)}:{s['name']}"
    return f"{str(kind).lower()}:{s.get('name')}"


def export_kubernetes(kubectl: Kubectl = run_kubectl, *, all_bindings: bool = False) -> dict[str, list[str]]:
    """-> {"<namespace>/<level>": sorted user names}. By default only bindings labelled
    managed-by=access-as-code; `all_bindings` also reads unlabelled ones bound to view/edit/admin."""
    args = ["get", "rolebindings", "--all-namespaces", "-o", "json"]
    if not all_bindings:
        args[3:3] = ["-l", "managed-by=access-as-code"]
    try:
        items = json.loads(kubectl(args)).get("items", [])
    except json.JSONDecodeError as exc:
        raise ExportError(f"kubectl returned invalid JSON: {exc}") from exc
    out: dict[str, set[str]] = {}
    for rb in items:
        ref = rb.get("roleRef", {})
        if ref.get("kind") != "ClusterRole" or ref.get("name") not in K8S_LEVELS:
            continue
        users = {_subject(s, rb["metadata"]["namespace"]) for s in rb.get("subjects") or []}
        key = f"{rb['metadata']['namespace']}/{ref['name']}"
        out.setdefault(key, set()).update(users)
    return {k: sorted(v) for k, v in sorted(out.items())}


def export_gitlab(
    url: str,
    token: str,
    teams: list[str],
    *,
    group_prefix: str = "",
    missing_ok: bool = False,
    fetch: Fetch = http_fetch,
) -> dict[str, dict[str, str]]:
    """-> {team: {username: level}} from the direct members of GitLab group `<prefix><team>`.
    A missing group is an error unless `missing_ok`, then the team is omitted (reported as missing)."""
    base = _base(url, "GITLAB_URL")
    hdr = {"PRIVATE-TOKEN": token}
    out: dict[str, dict[str, str]] = {}
    for team in sorted(teams):
        gid = urllib.parse.quote(f"{group_prefix}{team}", safe="")
        members: dict[str, str] = {}
        page = "1"
        try:
            while page:
                body, headers = fetch(
                    f"{base}/api/v4/groups/{gid}/members?per_page=100&page={page}", hdr, "GET"
                )
                for m in body:
                    members[m["username"]] = GITLAB_LEVELS.get(
                        m["access_level"], f"level-{m['access_level']}"
                    )
                page = headers.get("x-next-page", "")
        except NotFound as exc:
            if missing_ok:
                continue
            raise ExportError(
                f"GitLab group '{group_prefix}{team}' not found or not visible to the token "
                "(check --gitlab-group-prefix and token scope, or pass --gitlab-missing-ok)"
            ) from exc
        out[team] = dict(sorted(members.items()))
    return out


def export_state(
    teams: list[str],
    *,
    vault: tuple[str, str] | None = None,
    kubernetes: bool = False,
    k8s_all: bool = False,
    gitlab: tuple[str, str] | None = None,
    gitlab_prefix: str = "",
    gitlab_missing_ok: bool = False,
    fetch: Fetch = http_fetch,
    kubectl: Kubectl = run_kubectl,
) -> dict[str, Any]:
    """Only the requested systems appear in the result; `diff` does not check the others."""
    state: dict[str, Any] = {}
    if vault:
        state["vault_policies"], state["vault_groups"] = export_vault(*vault, fetch=fetch)
    if kubernetes:
        state["kubernetes"] = export_kubernetes(kubectl, all_bindings=k8s_all)
    if gitlab:
        state["gitlab"] = export_gitlab(
            *gitlab, teams, group_prefix=gitlab_prefix, missing_ok=gitlab_missing_ok, fetch=fetch
        )
    return state
