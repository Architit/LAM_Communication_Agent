from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_required_governance_files_exist():
    required = [
        "INTERACTION_PROTOCOL.md",
        "ROADMAP.md",
        "DEV_LOGS.md",
        "WORKFLOW_SNAPSHOT_CONTRACT.md",
        "WORKFLOW_SNAPSHOT_STATE.md",
        "SYSTEM_STATE_CONTRACT.md",
        "SYSTEM_STATE.md",
        "GATEWAY_ACCESS_CONTRACT.md",
    ]
    missing = [name for name in required if not (REPO_ROOT / name).is_file()]
    assert missing == []


def test_protocol_sync_header_present():
    text = (REPO_ROOT / "INTERACTION_PROTOCOL.md").read_text(encoding="utf-8")
    assert "protocol_source: RADRILONIUMA-PROJECT" in text
    assert "protocol_version: v1.0.0" in text
