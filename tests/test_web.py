from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from paperflow.web import create_app


def docx_bytes(text: str = "用于网页测试的中文段落") -> bytes:
    stream = BytesIO()
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            f"<w:document xmlns:w='{namespace}'><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return stream.getvalue()


def test_existing_chinese_web_flow(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    client = TestClient(create_app(root, execute_agents=False, codex_path="/missing/codex"))

    home = client.get("/")
    assert home.status_code == 200
    assert "建立第一篇论文" in home.text

    created = client.post(
        "/papers",
        data={"title": "网页论文", "slug": "web-paper", "entry": "existing_chinese", "year": "2026"},
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert "上传中文原稿" in created.text

    uploaded = client.post(
        "/papers/P-2026-001/source",
        files={"source": ("source.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        follow_redirects=True,
    )
    assert uploaded.status_code == 200
    assert "提取 1 个内容单元" in uploaded.text
    assert "确认研究范围" in uploaded.text

    approved = client.post(
        "/papers/P-2026-001/gates/G0/approve",
        data={"note": "人工确认原稿范围"},
        follow_redirects=True,
    )
    assert approved.status_code == 200
    assert "交给 Agent 准备译文" in approved.text


def test_new_research_web_flow_and_local_security(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    client = TestClient(create_app(root, execute_agents=False, codex_path="/missing/codex"))
    client.post(
        "/papers",
        data={"title": "研究项目", "slug": "research", "entry": "new_research", "year": "2026"},
    )
    saved = client.post(
        "/papers/P-2026-001/research-question",
        data={"question": "Does it work?", "assumptions": "Controlled setting", "data_source": "Local data", "limitations": "Small sample"},
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert "确认研究范围" in saved.text

    blocked = client.post(
        "/papers/P-2026-001/advance",
        headers={"origin": "https://attacker.example"},
    )
    assert blocked.status_code == 403

    missing = client.get("/papers/P-2026-001/files/../../pyproject.toml")
    assert missing.status_code in {404, 405}


def test_web_can_create_recoverable_agent_job_without_running_it(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    app = create_app(root, execute_agents=False, codex_path="/missing/codex")
    client = TestClient(app)
    client.post(
        "/papers",
        data={"title": "Agent UI", "slug": "agent-ui", "entry": "new_research", "year": "2026"},
    )
    response = client.post(
        "/papers/P-2026-001/agent",
        data={"prompt": "检查项目并生成 QA 报告"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "等待 Agent 开始" in response.text
    jobs = app.state.jobs.list_jobs("P-2026-001")
    assert len(jobs) == 1 and jobs[0]["status"] == "queued"


def test_translation_review_page_updates_human_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    client = TestClient(create_app(root, execute_agents=False, codex_path="/missing/codex"))
    client.post(
        "/papers",
        data={"title": "翻译页面", "slug": "translation-ui", "entry": "existing_chinese", "year": "2026"},
    )
    client.post(
        "/papers/P-2026-001/source",
        files={"source": ("source.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post("/papers/P-2026-001/gates/G0/approve", data={"note": "人工确认"})
    page = client.get("/papers/P-2026-001/translation")
    assert page.status_code == 200 and "中英对照审核" in page.text
    saved = client.post(
        "/papers/P-2026-001/translation/U000001",
        data={"final_en": "Confirmed text.", "change_reason": "人工审核", "confirm": "yes"},
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert "0/1" not in saved.text
