"""kitefrost-gn-audit: local file collection + CI exit codes (GN-IMP-7)."""

from __future__ import annotations

import json

import pytest
from kitefrost_game_narrative import audit


class _Continuity:
    def __init__(self, result):
        self.result, self.bodies = result, []

    def audit_files(self, project_id, body):
        self.bodies.append((project_id, body))
        return self.result


class _Client:
    def __init__(self, result):
        self.continuity = _Continuity(result)


def _tree(tmp_path):
    (tmp_path / "act1").mkdir(parents=True)
    (tmp_path / "act1" / "a.ink").write_text('VAR x = "dead"\n')
    (tmp_path / "b.yarn").write_text("<<declare $y = true>>\n")
    (tmp_path / "notes.md").write_text("ignored")
    return tmp_path


def test_collects_only_ink_and_yarn_with_relative_paths(tmp_path):
    files = audit.collect_files(_tree(tmp_path))
    assert sorted(f["path"] for f in files) == ["act1/a.ink", "b.yarn"]


def test_audit_path_sends_files_and_entities(tmp_path):
    c = _Client({"report": {"findings": []}, "files_audited": 2})
    audit.audit_path(c, "p1", _tree(tmp_path), entities={"x": ["npc", "a", "status"]}, sarif=True)
    pid, body = c.continuity.bodies[0]
    assert (
        pid == "p1" and body["sarif"] is True and body["entities"] == {"x": ["npc", "a", "status"]}
    )


def test_empty_directory_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        audit.audit_path(_Client({}), "p1", tmp_path)


@pytest.mark.parametrize(
    ("severities", "fail_on", "n"),
    [
        (["error"], "error", 1),
        (["warning"], "error", 0),
        (["warning"], "warning", 1),
        ([], "info", 0),
    ],
)
def test_fail_on_threshold(severities, fail_on, n):
    result = {"report": {"findings": [{"severity": s, "message": "m"} for s in severities]}}
    assert len(audit.failing_findings(result, fail_on)) == n


def test_cli_exit_codes_and_sarif_file(tmp_path, monkeypatch):
    tree = _tree(tmp_path / "src")
    sarif_path = tmp_path / "out.sarif"
    result = {
        "report": {"findings": [{"severity": "error", "message": "dead NPC speaks"}]},
        "files_audited": 2,
        "variables_found": 3,
        "variables_bound": 2,
        "sarif": {"version": "2.1.0"},
    }
    monkeypatch.setenv("KITEFROST_API_KEY", "sk_test")
    monkeypatch.setattr(
        "kitefrost_game_narrative.client.GameNarrativeClient.from_api_key",
        lambda k: _Client(result),
    )
    assert audit.main([str(tree), "--project", "p1", "--sarif", str(sarif_path)]) == 1
    assert json.loads(sarif_path.read_text())["version"] == "2.1.0"
    result["report"]["findings"] = []
    assert audit.main([str(tree), "--project", "p1"]) == 0


def test_cli_without_api_key_exits_2(tmp_path, monkeypatch):
    monkeypatch.delenv("KITEFROST_API_KEY", raising=False)
    assert audit.main([str(_tree(tmp_path)), "--project", "p1"]) == 2


def test_cli_exits_3_when_nothing_was_checked(tmp_path, monkeypatch):
    """FND-20260929-56F: 0 findings over 0 bound variables is not a pass."""
    result = {
        "report": {"findings": []},
        "files_audited": 1,
        "variables_found": 4,
        "variables_bound": 0,
    }
    monkeypatch.setenv("KITEFROST_API_KEY", "sk_test")
    monkeypatch.setattr(
        "kitefrost_game_narrative.client.GameNarrativeClient.from_api_key",
        lambda k: _Client(result),
    )
    assert audit.main([str(_tree(tmp_path / "s")), "--project", "p1"]) == 3
