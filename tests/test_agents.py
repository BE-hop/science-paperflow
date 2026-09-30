from __future__ import annotations

from pathlib import Path

import pytest

from paperflow.agents import AgentJobManager
from paperflow.core import PaperflowError, create_paper


def test_agent_output_is_staged_then_applied(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    paper = create_paper(root, title="Agent test", slug="agent-test", entry="new_research", year=2026)
    manager = AgentJobManager(root, execute=False)
    job = manager.create("P-2026-001", "检查项目并生成 QA 报告")
    staged = manager.job_dir(job["job_id"]) / "workspace/papers" / paper.name
    (staged / "qa/agent-report.md").write_text("# QA\n\nCandidate report.\n", encoding="utf-8")

    manager._collect_result(
        job["job_id"],
        {"status": "completed", "summary": "完成", "changed_files": [], "checks": [], "questions": []},
    )
    assert not (paper / "qa/agent-report.md").exists()
    assert manager.load(job["job_id"])["changed_files"] == ["qa/agent-report.md"]

    manager.apply(job["job_id"])
    assert (paper / "qa/agent-report.md").is_file()
    assert manager.load(job["job_id"])["status"] == "applied"


def test_agent_cannot_modify_authoritative_state(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    paper = create_paper(root, title="Guard", slug="guard", entry="new_research", year=2026)
    manager = AgentJobManager(root, execute=False)
    job = manager.create("P-2026-001", "检查项目")
    staged = manager.job_dir(job["job_id"]) / "workspace/papers" / paper.name
    (staged / "PAPER.yaml").write_text("changed: true\n", encoding="utf-8")
    with pytest.raises(PaperflowError, match="受保护"):
        manager._collect_result(
            job["job_id"],
            {"status": "completed", "summary": "完成", "changed_files": [], "checks": [], "questions": []},
        )
    assert "paper_id" in (paper / "PAPER.yaml").read_text(encoding="utf-8")


def test_agent_apply_detects_concurrent_change(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    paper = create_paper(root, title="Conflict", slug="conflict", entry="new_research", year=2026)
    manager = AgentJobManager(root, execute=False)
    job = manager.create("P-2026-001", "检查项目")
    staged = manager.job_dir(job["job_id"]) / "workspace/papers" / paper.name
    (staged / "qa/report.md").write_text("agent version", encoding="utf-8")
    manager._collect_result(
        job["job_id"],
        {"status": "completed", "summary": "完成", "changed_files": [], "checks": [], "questions": []},
    )
    (paper / "qa/report.md").write_text("user version", encoding="utf-8")
    with pytest.raises(PaperflowError, match="已变化"):
        manager.apply(job["job_id"])
    assert (paper / "qa/report.md").read_text(encoding="utf-8") == "user version"
