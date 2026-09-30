from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import (
    GATES,
    CheckIssue,
    PaperflowError,
    approve_gate,
    check_paper,
    create_paper,
    extract_translation_units,
    freeze_source,
    gate_readiness_issues,
    init_journal,
    paper_dirs,
    read_paper,
    record_journal_qa,
    rebuild_portfolio,
    resolve_paper,
    set_status,
)


MAX_UPLOAD_BYTES = 100 * 1024 * 1024
SAFE_UPLOAD_SUFFIXES = {
    ".docx",
    ".pdf",
    ".xlsx",
    ".xls",
    ".csv",
    ".tsv",
    ".txt",
    ".md",
    ".bib",
    ".ris",
    ".zip",
}


@dataclass(frozen=True)
class NextAction:
    key: str
    label: str
    description: str


def safe_upload_name(filename: str) -> str:
    leaf = Path(filename or "").name.strip()
    if not leaf or leaf in {".", ".."}:
        raise PaperflowError("请选择有效文件")
    suffix = Path(leaf).suffix.casefold()
    if suffix not in SAFE_UPLOAD_SUFFIXES:
        raise PaperflowError(f"不支持的文件类型：{suffix or '无扩展名'}")
    stem = re.sub(r"[^\w-]+", "-", Path(leaf).stem, flags=re.UNICODE).strip("-_") or "upload"
    return f"{stem}{suffix}"


def _temp_upload(filename: str, content: bytes) -> Path:
    if not content:
        raise PaperflowError("上传文件为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise PaperflowError("上传文件超过 100 MB 限制")
    safe_name = safe_upload_name(filename)
    directory = Path(tempfile.mkdtemp(prefix="paperflow-upload-"))
    path = directory / safe_name
    path.write_bytes(content)
    return path


def create_project(root: Path, *, title: str, entry: str, year: int, slug: str | None = None) -> Path:
    title = title.strip()
    if not title:
        raise PaperflowError("请填写论文标题")
    generated_slug = slug or re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or f"paper-{year}"
    return create_paper(root, title=title, slug=generated_slug, entry=entry, year=year)


def register_source_upload(root: Path, identifier: str, filename: str, content: bytes, *, extract: bool = True) -> tuple[Path, int]:
    safe_name = safe_upload_name(filename)
    temp_path = _temp_upload(safe_name, content)
    try:
        frozen = freeze_source(root, identifier, temp_path)
    finally:
        shutil.rmtree(temp_path.parent, ignore_errors=True)
    count = 0
    if extract and frozen.suffix.casefold() == ".docx":
        folder = resolve_paper(root, identifier)
        segments = folder / "02_translation" / "segments.jsonl"
        if not segments.read_text(encoding="utf-8").strip():
            count = extract_translation_units(root, identifier, frozen.name)
    return frozen, count


def save_research_question(
    root: Path,
    identifier: str,
    *,
    question: str,
    assumptions: str = "",
    data_source: str = "",
    limitations: str = "",
) -> Path:
    if not question.strip():
        raise PaperflowError("研究问题不能为空")
    folder = resolve_paper(root, identifier)
    path = folder / "01_research" / "research-question.md"
    body = "\n".join(
        [
            "# Research question",
            "",
            question.strip(),
            "",
            "## Assumptions",
            "",
            assumptions.strip() or "UNRESOLVED",
            "",
            "## Data source",
            "",
            data_source.strip() or "UNRESOLVED",
            "",
            "## Limitations",
            "",
            limitations.strip() or "UNRESOLVED",
            "",
        ]
    )
    path.write_text(body, encoding="utf-8")
    return path


def save_master_upload(root: Path, identifier: str, filename: str, content: bytes) -> Path:
    safe_name = safe_upload_name(filename)
    if Path(safe_name).suffix.casefold() != ".docx":
        raise PaperflowError("英文主稿必须是 DOCX 文件")
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise PaperflowError("英文主稿为空或超过 100 MB")
    folder = resolve_paper(root, identifier)
    target = folder / "03_manuscript" / "master_en.docx"
    if target.exists():
        raise PaperflowError("英文主稿已存在；请交给 Agent 生成新版本或先人工确认版本策略")
    target.write_bytes(content)
    rebuild_portfolio(root)
    return target


def save_submission_upload(root: Path, identifier: str, filename: str, content: bytes) -> Path:
    safe_name = safe_upload_name(filename)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise PaperflowError("投稿文件为空或超过 100 MB")
    folder = resolve_paper(root, identifier)
    target = folder / "05_submission" / safe_name
    if target.exists():
        raise PaperflowError(f"拒绝覆盖已有投稿文件：{safe_name}")
    target.write_bytes(content)
    rebuild_portfolio(root)
    return target


def save_review_upload(root: Path, identifier: str, round_name: str, filename: str, content: bytes) -> Path:
    safe_name = safe_upload_name(filename)
    safe_round = re.sub(r"[^A-Za-z0-9_-]+", "-", round_name.strip()).strip("-") or "R1"
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise PaperflowError("审稿文件为空或超过 100 MB")
    folder = resolve_paper(root, identifier)
    target = folder / "06_reviews" / safe_round / safe_name
    if target.exists():
        raise PaperflowError(f"拒绝覆盖已有审稿文件：{safe_round}/{safe_name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    rebuild_portfolio(root)
    return target


def create_journal_from_upload(
    root: Path,
    identifier: str,
    *,
    journal: str,
    article_type: str,
    guidelines_url: str,
    verified_at: str,
    template_name: str | None = None,
    template_content: bytes | None = None,
) -> Path:
    template_path: Path | None = None
    if template_name and template_content:
        safe_name = safe_upload_name(template_name)
        template_path = _temp_upload(safe_name, template_content)
    try:
        return init_journal(
            root,
            identifier,
            journal=journal.strip(),
            article_type=article_type.strip(),
            guidelines_url=guidelines_url.strip(),
            verified_at=verified_at.strip(),
            template=template_path,
        )
    finally:
        if template_path is not None:
            shutil.rmtree(template_path.parent, ignore_errors=True)


def record_user_journal_review(
    root: Path,
    identifier: str,
    journal_id: str,
    *,
    structural_evidence: str,
    render_evidence: str,
    reviewer: str,
) -> None:
    if not structural_evidence.strip():
        raise PaperflowError("请填写结构检查证据路径或说明")
    if not render_evidence.strip() or not reviewer.strip():
        raise PaperflowError("全页视觉检查必须填写检查人和证据")
    record_journal_qa(
        root,
        identifier,
        journal_id,
        check="structural_audit",
        passed=True,
        evidence=structural_evidence.strip(),
    )
    record_journal_qa(
        root,
        identifier,
        journal_id,
        check="render_review",
        passed=True,
        evidence=render_evidence.strip(),
        reviewer=reviewer.strip(),
    )


def approve_user_gate(root: Path, identifier: str, gate: str, note: str) -> None:
    if not note.strip():
        raise PaperflowError("人工批准必须填写确认说明")
    approve_gate(root, identifier, gate, note.strip())


def advance_project_status(root: Path, identifier: str) -> str:
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    current = str(paper.get("overall_status"))
    preferred = {
        "idea": "exploring",
        "exploring": "drafting",
        "drafting": "translating" if paper.get("entry_path") == "existing_chinese" else "journal_targeting",
        "translating": "language_review",
        "language_review": "journal_targeting",
        "journal_targeting": "formatting",
        "formatting": "internal_review",
        "internal_review": "ready_to_submit",
        "ready_to_submit": "submitted",
        "submitted": "under_review",
        "revision": "internal_review",
        "rejected": "journal_targeting",
        "parked": "drafting",
    }
    target = preferred.get(current)
    if not target:
        raise PaperflowError(f"当前状态 {current} 没有可自动建议的下一阶段")
    set_status(root, identifier, target)
    return target


def _jsonl_count(path: Path) -> tuple[int, int, int]:
    total = confirmed = candidates = 0
    if not path.exists():
        return total, confirmed, candidates
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        if item.get("status") in {"confirmed", "not_applicable"}:
            confirmed += 1
        if str(item.get("candidate_en", "")).strip() or str(item.get("final_en", "")).strip():
            candidates += 1
    return total, confirmed, candidates


def translation_segments(root: Path, identifier: str, *, view: str = "pending") -> list[dict[str, Any]]:
    folder = resolve_paper(root, identifier)
    path = folder / "02_translation" / "segments.jsonl"
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if view == "risk" and not (item.get("terminology_risks") or item.get("fact_risks")):
            continue
        if view == "pending" and item.get("status") in {"confirmed", "not_applicable"}:
            continue
        records.append(item)
    return records


def update_translation_segment(
    root: Path,
    identifier: str,
    *,
    unit_id: str,
    final_en: str,
    change_reason: str,
    confirm: bool,
) -> None:
    folder = resolve_paper(root, identifier)
    path = folder / "02_translation" / "segments.jsonl"
    records = translation_segments(root, identifier, view="all")
    match = next((item for item in records if str(item.get("unit_id")) == unit_id), None)
    if match is None:
        raise PaperflowError(f"未找到翻译单元：{unit_id}")
    if confirm and not final_en.strip():
        raise PaperflowError("确认翻译前必须填写最终英文")
    match["final_en"] = final_en.strip()
    match["change_reason"] = change_reason.strip()
    match["status"] = "confirmed" if confirm else "review"
    rendered = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    os.replace(temporary, path)
    rebuild_portfolio(root)


def stage_summary(folder: Path, paper: dict[str, Any]) -> list[dict[str, Any]]:
    gates = paper.get("gates", {})
    definitions = (
        ("setup", "建立项目", "G0"),
        ("content", "准备论文内容", "G1"),
        ("journal", "选择目标期刊", "G3"),
        ("submission", "准备投稿", "G4"),
        ("review", "审稿与返修", "G5"),
    )
    first_open = next((gate for _, _, gate in definitions if not gates.get(gate, {}).get("approved")), None)
    stages = []
    for key, label, gate in definitions:
        approved = bool(gates.get(gate, {}).get("approved"))
        state = "complete" if approved else "current" if gate == first_open else "upcoming"
        stages.append({"key": key, "label": label, "gate": gate, "state": state})
    return stages


def next_action(folder: Path, paper: dict[str, Any]) -> NextAction:
    gates = paper.get("gates", {})
    if not gates.get("G0", {}).get("approved"):
        if paper.get("entry_path") == "existing_chinese" and not paper.get("source_files"):
            return NextAction("upload_source", "上传中文原稿", "系统将冻结原稿并自动提取可翻译内容。")
        if paper.get("entry_path") == "new_research":
            question = folder / "01_research" / "research-question.md"
            if not question.exists() or not question.read_text(encoding="utf-8").strip():
                return NextAction("research_question", "填写研究问题", "先明确研究问题、假设、数据来源和限制。")
        return NextAction("approve_G0", "确认研究范围", "检查输入材料后，由你批准第一个人工关卡。")

    total, confirmed, candidates = _jsonl_count(folder / "02_translation" / "segments.jsonl")
    if not gates.get("G1", {}).get("approved"):
        if paper.get("entry_path") == "existing_chinese" and total and confirmed < total:
            if candidates > confirmed:
                return NextAction("review_translation", "审核候选译文", f"Agent 已准备候选内容；当前已确认 {confirmed}/{total} 个单元。")
            return NextAction("agent_translation", "交给 Agent 准备译文", f"当前已确认 {confirmed}/{total} 个内容单元。")
        if not (folder / "03_manuscript" / "master_en.docx").exists():
            return NextAction("master", "准备英文主稿", "上传已有英文主稿，或交给 Agent 生成候选稿。")
        return NextAction("approve_G1", "确认英文内容", "由你确认英文主稿、术语和科学含义。")

    profiles = paper.get("journal_profiles", [])
    if not profiles:
        return NextAction("journal", "登记目标期刊", "填写期刊官方页面并上传官方模板。")
    if not gates.get("G2", {}).get("approved"):
        return NextAction("approve_G2", "确认目标期刊", "由你确认期刊、稿件类型和官方要求。")
    if not gates.get("G3", {}).get("approved"):
        if not gate_readiness_issues(folder, paper, "G3"):
            return NextAction("approve_G3", "确认期刊稿与版式", "结构检查和人工视觉检查材料已齐备，由你批准 G3。")
        active_profile = None
        for record in profiles:
            profile = load_yaml(folder / str(record.get("path", "")))
            if profile.get("status", "active") == "active":
                active_profile = profile
                break
        if active_profile and (folder / str(active_profile.get("derived_manuscript", ""))).is_file():
            return NextAction("journal_qa", "审核期刊稿与页面", "登记真实完成的结构检查和人工全页视觉检查。")
        return NextAction("agent_journal", "交给 Agent 准备期刊稿", "Agent 将在隔离副本中整理模板、派生稿和 QA 材料。")
    if not gates.get("G4", {}).get("approved"):
        if not list((folder / "05_submission").glob("*")):
            return NextAction("submission", "加入投稿文件", "上传准备提交的稿件和附件。")
        return NextAction("check_submission", "检查并确认投稿包", "系统检查投稿残留和必需文件，由你最终确认。")
    if not gates.get("G5", {}).get("approved"):
        rounds = [path for path in (folder / "06_reviews").iterdir() if path.is_dir()]
        if not rounds:
            return NextAction("review_upload", "加入审稿材料", "上传编辑信或审稿意见，历史轮次会独立保留。")
        if not gate_readiness_issues(folder, paper, "G5"):
            return NextAction("approve_G5", "确认返修材料", "由你审核回复和返修稿后批准 G5。")
        return NextAction("agent_review", "整理审稿与返修", "上传审稿材料后让 Agent 整理问题和候选回复。")
    return NextAction("complete", "查看项目记录", "当前人工关卡均已完成。")


def paper_detail(root: Path, identifier: str) -> dict[str, Any]:
    folder = resolve_paper(root, identifier)
    paper = read_paper(folder)
    stages = stage_summary(folder, paper)
    action = next_action(folder, paper)
    total, confirmed, candidates = _jsonl_count(folder / "02_translation" / "segments.jsonl")
    approved = sum(bool(paper.get("gates", {}).get(gate, {}).get("approved")) for gate in GATES)
    active_journal = None
    for record in paper.get("journal_profiles", []):
        profile = load_yaml(folder / str(record.get("path", "")))
        if profile.get("status", "active") == "active":
            active_journal = profile
            break
    return {
        "folder": folder,
        "paper": paper,
        "stages": stages,
        "current_stage": next((item for item in stages if item["state"] == "current"), stages[-1]),
        "next_action": action,
        "progress": round(approved / len(GATES) * 100),
        "translation_total": total,
        "translation_confirmed": confirmed,
        "translation_candidates": candidates,
        "active_journal": active_journal,
        "issues": check_paper(root, identifier),
        "gate_readiness": {
            gate: gate_readiness_issues(folder, paper, gate)
            for gate in GATES
            if not paper.get("gates", {}).get(gate, {}).get("approved")
        },
    }


def portfolio_cards(root: Path) -> list[dict[str, Any]]:
    cards = []
    for folder in paper_dirs(root):
        detail = paper_detail(root, str(read_paper(folder).get("paper_id")))
        paper = detail["paper"]
        cards.append(
            {
                "paper_id": paper.get("paper_id"),
                "title": paper.get("title"),
                "overall_status": paper.get("overall_status"),
                "current_stage": detail["current_stage"],
                "next_action": detail["next_action"],
                "progress": detail["progress"],
                "blockers": paper.get("blockers", []),
                "issue_count": sum(issue.severity == "error" for issue in detail["issues"]),
            }
        )
    return cards


def issue_dicts(issues: list[CheckIssue]) -> list[dict[str, str]]:
    return [{"severity": item.severity, "code": item.code, "message": item.message} for item in issues]
