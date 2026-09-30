from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from paperflow.core import PaperflowError, load_yaml
from paperflow.service import (
    create_project,
    create_journal_from_upload,
    paper_detail,
    register_source_upload,
    record_user_journal_review,
    safe_upload_name,
    save_research_question,
    translation_segments,
    update_translation_segment,
)


def docx_bytes(text: str = "中文段落") -> bytes:
    from io import BytesIO

    stream = BytesIO()
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            f"<w:document xmlns:w='{namespace}'><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return stream.getvalue()


def test_existing_paper_next_action_and_upload(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    create_project(root, title="中文研究", slug="study", entry="existing_chinese", year=2026)
    detail = paper_detail(root, "P-2026-001")
    assert detail["next_action"].key == "upload_source"

    frozen, count = register_source_upload(root, "P-2026-001", "../source.docx", docx_bytes())
    assert frozen.name == "source.docx"
    assert count == 1
    assert paper_detail(root, "P-2026-001")["next_action"].key == "approve_G0"
    assert load_yaml(root / "P-2026-001-study/PAPER.yaml")["source_files"][0]["sha256"]


def test_new_research_question_drives_next_action(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    create_project(root, title="New research", slug="research", entry="new_research", year=2026)
    assert paper_detail(root, "P-2026-001")["next_action"].key == "research_question"
    path = save_research_question(root, "P-2026-001", question="Does the intervention work?")
    assert "UNRESOLVED" in path.read_text(encoding="utf-8")
    assert paper_detail(root, "P-2026-001")["next_action"].key == "approve_G0"


def test_upload_name_is_sanitized_and_restricted() -> None:
    assert safe_upload_name("../../中文 稿件.docx") == "中文-稿件.docx"
    with pytest.raises(PaperflowError, match="不支持"):
        safe_upload_name("payload.exe")


def test_translation_candidate_can_be_reviewed_and_confirmed(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    create_project(root, title="翻译审核", slug="translation-review", entry="existing_chinese", year=2026)
    register_source_upload(root, "P-2026-001", "source.docx", docx_bytes())
    path = root / "P-2026-001-translation-review/02_translation/segments.jsonl"
    text = path.read_text(encoding="utf-8").replace('"candidate_en": ""', '"candidate_en": "Candidate"')
    path.write_text(text, encoding="utf-8")
    assert paper_detail(root, "P-2026-001")["next_action"].key == "approve_G0"

    from paperflow.service import approve_user_gate

    approve_user_gate(root, "P-2026-001", "G0", "确认源稿")
    assert paper_detail(root, "P-2026-001")["next_action"].key == "review_translation"
    unit_id = translation_segments(root, "P-2026-001", view="pending")[0]["unit_id"]
    update_translation_segment(
        root,
        "P-2026-001",
        unit_id=unit_id,
        final_en="Confirmed translation.",
        change_reason="人工确认",
        confirm=True,
    )
    assert translation_segments(root, "P-2026-001", view="pending") == []


def test_user_can_record_real_journal_review(tmp_path: Path) -> None:
    root = tmp_path / "papers"
    create_project(root, title="期刊审核", slug="journal-review", entry="new_research", year=2026)
    journal_dir = create_journal_from_upload(
        root,
        "P-2026-001",
        journal="Example Journal",
        article_type="Original Article",
        guidelines_url="https://journal.example/guidelines",
        verified_at="2026-08-05",
    )
    record_user_journal_review(
        root,
        "P-2026-001",
        "example-journal",
        structural_evidence="qa/structure.md",
        render_evidence="qa/render.md",
        reviewer="Researcher",
    )
    profile = load_yaml(journal_dir / "journal.yaml")
    assert profile["qa"]["structural_audit"]["passed"] is True
    assert profile["qa"]["render_review"]["reviewer"] == "Researcher"
