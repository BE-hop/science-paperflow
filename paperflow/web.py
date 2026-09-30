from __future__ import annotations

import asyncio
import json
import socket
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .agents import ACTIVE_STATUSES, TERMINAL_STATUSES, AgentJobManager, agent_available
from .core import PaperflowError, check_paper, resolve_paper
from .service import (
    advance_project_status,
    approve_user_gate,
    create_journal_from_upload,
    create_project,
    issue_dicts,
    paper_detail,
    portfolio_cards,
    record_user_journal_review,
    register_source_upload,
    safe_upload_name,
    save_master_upload,
    save_research_question,
    save_review_upload,
    save_submission_upload,
    translation_segments,
    update_translation_segment,
)


PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def _redirect(path: str, *, message: str = "", error: str = "") -> RedirectResponse:
    parts = []
    if message:
        parts.append(f"message={quote(message)}")
    if error:
        parts.append(f"error={quote(error)}")
    suffix = f"?{'&'.join(parts)}" if parts else ""
    return RedirectResponse(f"{path}{suffix}", status_code=303)


def _read_upload(upload: UploadFile | None) -> tuple[str | None, bytes | None]:
    if upload is None or not upload.filename:
        return None, None
    safe_name = safe_upload_name(upload.filename)
    content = upload.file.read()
    return safe_name, content


def create_app(root: Path | str | None = None, *, execute_agents: bool = True, codex_path: str | None = None) -> FastAPI:
    papers_root = Path(root or Path.cwd() / "papers").expanduser().resolve()
    papers_root.mkdir(parents=True, exist_ok=True)
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    manager = AgentJobManager(papers_root, codex_path=codex_path, execute=execute_agents)
    app = FastAPI(title="Paperflow", docs_url=None, redoc_url=None)
    app.state.papers_root = papers_root
    app.state.jobs = manager
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":", 1)[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return HTMLResponse("Paperflow 仅允许本机访问", status_code=403)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            if not origin.startswith(("http://127.0.0.1", "http://localhost", "http://testserver")):
                return HTMLResponse("拒绝跨站操作", status_code=403)
        return await call_next(request)

    @app.exception_handler(PaperflowError)
    async def paperflow_error(_request: Request, exc: PaperflowError):
        return HTMLResponse(f"<h1>操作未完成</h1><p>{exc}</p><p><a href='/'>返回工作台</a></p>", status_code=400)

    def context(request: Request, **values):
        available, reason = agent_available(codex_path)
        return {
            "request": request,
            "agent_available": available,
            "agent_reason": reason,
            "message": request.query_params.get("message", ""),
            "error": request.query_params.get("error", ""),
            **values,
        }

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        cards = portfolio_cards(papers_root)
        active = {str(job["paper_id"]): job for job in manager.list_jobs() if job.get("status") in ACTIVE_STATUSES}
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            context(request, cards=cards, active_jobs=active),
        )

    @app.get("/papers/new", response_class=HTMLResponse)
    async def new_paper_form(request: Request):
        return templates.TemplateResponse(
            request,
            "new_paper.html",
            context(request, current_year=datetime.now().year),
        )

    @app.post("/papers")
    async def new_paper(
        title: Annotated[str, Form()],
        entry: Annotated[str, Form()],
        year: Annotated[int, Form()],
        slug: Annotated[str, Form()] = "",
    ):
        try:
            folder = create_project(papers_root, title=title, entry=entry, year=year, slug=slug or None)
            paper_id = folder.name[:10]
            return _redirect(f"/papers/{paper_id}", message="论文项目已建立")
        except PaperflowError as exc:
            return _redirect("/papers/new", error=str(exc))

    @app.get("/papers/{paper_id}", response_class=HTMLResponse)
    async def paper_page(request: Request, paper_id: str):
        try:
            detail = paper_detail(papers_root, paper_id)
        except PaperflowError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        jobs = manager.list_jobs(paper_id)
        return templates.TemplateResponse(
            request,
            "paper.html",
            context(request, detail=detail, jobs=jobs, active_job=manager.active_for_paper(paper_id)),
        )

    @app.post("/papers/{paper_id}/source")
    async def upload_source(paper_id: str, source: Annotated[UploadFile, File()]):
        try:
            name, content = _read_upload(source)
            _path, count = register_source_upload(papers_root, paper_id, name or "", content or b"")
            return _redirect(f"/papers/{paper_id}", message=f"原稿已冻结，提取 {count} 个内容单元")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.post("/papers/{paper_id}/research-question")
    async def research_question(
        paper_id: str,
        question: Annotated[str, Form()],
        assumptions: Annotated[str, Form()] = "",
        data_source: Annotated[str, Form()] = "",
        limitations: Annotated[str, Form()] = "",
    ):
        try:
            save_research_question(
                papers_root,
                paper_id,
                question=question,
                assumptions=assumptions,
                data_source=data_source,
                limitations=limitations,
            )
            return _redirect(f"/papers/{paper_id}", message="研究问题已保存")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.post("/papers/{paper_id}/master")
    async def upload_master(paper_id: str, document: Annotated[UploadFile, File()]):
        try:
            name, content = _read_upload(document)
            save_master_upload(papers_root, paper_id, name or "", content or b"")
            return _redirect(f"/papers/{paper_id}", message="英文主稿已登记")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.post("/papers/{paper_id}/journal")
    async def create_journal(
        paper_id: str,
        journal: Annotated[str, Form()],
        article_type: Annotated[str, Form()],
        guidelines_url: Annotated[str, Form()],
        verified_at: Annotated[str, Form()],
        template: UploadFile | None = File(default=None),
    ):
        try:
            name, content = _read_upload(template)
            create_journal_from_upload(
                papers_root,
                paper_id,
                journal=journal,
                article_type=article_type,
                guidelines_url=guidelines_url,
                verified_at=verified_at,
                template_name=name,
                template_content=content,
            )
            return _redirect(f"/papers/{paper_id}", message="目标期刊已登记")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.post("/papers/{paper_id}/submission")
    async def upload_submission(paper_id: str, document: Annotated[UploadFile, File()]):
        try:
            name, content = _read_upload(document)
            save_submission_upload(papers_root, paper_id, name or "", content or b"")
            return _redirect(f"/papers/{paper_id}", message="投稿文件已加入")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.post("/papers/{paper_id}/journals/{journal_id}/qa")
    async def journal_review(
        paper_id: str,
        journal_id: str,
        structural_evidence: Annotated[str, Form()],
        render_evidence: Annotated[str, Form()],
        reviewer: Annotated[str, Form()],
    ):
        try:
            record_user_journal_review(
                papers_root,
                paper_id,
                journal_id,
                structural_evidence=structural_evidence,
                render_evidence=render_evidence,
                reviewer=reviewer,
            )
            return _redirect(f"/papers/{paper_id}", message="期刊结构与全页视觉检查已登记")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.post("/papers/{paper_id}/reviews")
    async def upload_review(
        paper_id: str,
        round_name: Annotated[str, Form()],
        document: Annotated[UploadFile, File()],
    ):
        try:
            name, content = _read_upload(document)
            save_review_upload(papers_root, paper_id, round_name, name or "", content or b"")
            return _redirect(f"/papers/{paper_id}", message="审稿材料已加入独立轮次")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.get("/papers/{paper_id}/translation", response_class=HTMLResponse)
    async def translation_page(request: Request, paper_id: str, view: str = "pending"):
        if view not in {"pending", "risk", "all"}:
            view = "pending"
        detail = paper_detail(papers_root, paper_id)
        segments = translation_segments(papers_root, paper_id, view=view)
        return templates.TemplateResponse(
            request,
            "translation.html",
            context(request, detail=detail, segments=segments, view=view),
        )

    @app.post("/papers/{paper_id}/translation/{unit_id}")
    async def update_translation(
        paper_id: str,
        unit_id: str,
        final_en: Annotated[str, Form()] = "",
        change_reason: Annotated[str, Form()] = "",
        confirm: Annotated[str, Form()] = "",
    ):
        try:
            update_translation_segment(
                papers_root,
                paper_id,
                unit_id=unit_id,
                final_en=final_en,
                change_reason=change_reason,
                confirm=confirm == "yes",
            )
            return _redirect(f"/papers/{paper_id}/translation", message=f"{unit_id} 已保存")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}/translation", error=str(exc))

    @app.post("/papers/{paper_id}/gates/{gate}/approve")
    async def approve_gate_route(paper_id: str, gate: str, note: Annotated[str, Form()]):
        try:
            approve_user_gate(papers_root, paper_id, gate, note)
            return _redirect(f"/papers/{paper_id}", message=f"{gate} 已记录人工批准")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.post("/papers/{paper_id}/advance")
    async def advance(paper_id: str):
        try:
            target = advance_project_status(papers_root, paper_id)
            return _redirect(f"/papers/{paper_id}", message=f"论文已进入 {target}")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.get("/papers/{paper_id}/check", response_class=HTMLResponse)
    async def check_page(request: Request, paper_id: str):
        issues = issue_dicts(check_paper(papers_root, paper_id))
        detail = paper_detail(papers_root, paper_id)
        return templates.TemplateResponse(
            request,
            "check.html",
            context(request, issues=issues, detail=detail),
        )

    @app.get("/papers/{paper_id}/files", response_class=HTMLResponse)
    async def files_page(request: Request, paper_id: str):
        folder = resolve_paper(papers_root, paper_id)
        files = [
            {
                "path": path.relative_to(folder).as_posix(),
                "size": path.stat().st_size,
            }
            for path in sorted(folder.rglob("*"))
            if path.is_file()
        ]
        return templates.TemplateResponse(
            request,
            "files.html",
            context(request, paper=read_paper_safe(folder), files=files),
        )

    @app.get("/papers/{paper_id}/files/{relative_path:path}")
    async def download_file(paper_id: str, relative_path: str):
        folder = resolve_paper(papers_root, paper_id).resolve()
        target = (folder / relative_path).resolve()
        if folder not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(target, filename=target.name)

    @app.post("/papers/{paper_id}/agent")
    async def create_agent_job(paper_id: str, prompt: Annotated[str, Form()]):
        available, reason = agent_available(codex_path)
        if not available and execute_agents:
            return _redirect(f"/papers/{paper_id}", error=reason)
        try:
            job = manager.create(paper_id, prompt)
            return _redirect(f"/jobs/{job['job_id']}")
        except PaperflowError as exc:
            return _redirect(f"/papers/{paper_id}", error=str(exc))

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_page(request: Request, job_id: str):
        try:
            job = manager.load(job_id)
        except PaperflowError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "job.html", context(request, job=job))

    @app.get("/jobs/{job_id}/events")
    async def job_events(job_id: str):
        async def stream():
            previous = ""
            while True:
                try:
                    job = manager.load(job_id)
                except PaperflowError:
                    yield "event: error\ndata: {}\n\n"
                    return
                payload = json.dumps(
                    {
                        "status": job.get("status"),
                        "summary": job.get("summary"),
                        "changed_files": job.get("changed_files", []),
                        "questions": job.get("questions", []),
                    },
                    ensure_ascii=False,
                )
                if payload != previous:
                    yield f"data: {payload}\n\n"
                    previous = payload
                if job.get("status") in TERMINAL_STATUSES:
                    return
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/jobs/{job_id}/apply")
    async def apply_job(job_id: str):
        try:
            job = manager.apply(job_id)
            return _redirect(f"/papers/{job['paper_id']}", message="Agent 结果已接受并重新检查")
        except PaperflowError as exc:
            return _redirect(f"/jobs/{job_id}", error=str(exc))

    @app.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        try:
            manager.cancel(job_id)
            return _redirect(f"/jobs/{job_id}", message="Agent 任务已取消")
        except PaperflowError as exc:
            return _redirect(f"/jobs/{job_id}", error=str(exc))

    @app.post("/jobs/{job_id}/retry")
    async def retry_job(job_id: str):
        try:
            job = manager.retry(job_id)
            return _redirect(f"/jobs/{job['job_id']}")
        except PaperflowError as exc:
            return _redirect(f"/jobs/{job_id}", error=str(exc))

    return app


def read_paper_safe(folder: Path):
    from .core import read_paper

    return read_paper(folder)


def _available_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise PaperflowError("没有可用的本地端口")


def run_web(root: Path, *, port: int = 8765, open_browser: bool = True) -> None:
    selected_port = _available_port(port)
    url = f"http://127.0.0.1:{selected_port}"
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    print(f"Paperflow workbench: {url}")
    uvicorn.run(create_app(root), host="127.0.0.1", port=selected_port, log_level="warning")
