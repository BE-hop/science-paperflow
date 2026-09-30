from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from .core import PaperflowError, atomic_yaml, audit_docx, check_paper, load_yaml, now_iso, rebuild_portfolio, resolve_paper


TERMINAL_STATUSES = {"completed", "needs_user", "failed", "cancelled", "applied"}
ACTIVE_STATUSES = {"queued", "running"}
FORBIDDEN_PATTERNS = (
    "PAPER.yaml",
    "00_source/**",
    "04_journal/*/official/**",
    "05_submission/receipts/**",
)
ACTION_ALLOWLISTS = {
    "translation": ("02_translation/**", "03_manuscript/**", "qa/**"),
    "research": ("01_research/**", "evidence/**", "references/**", "qa/**"),
    "journal": ("04_journal/*/artifact.md", "04_journal/*/derived/**", "04_journal/*/qa/**", "qa/**"),
    "review": ("06_reviews/**", "decisions/**", "qa/**"),
    "audit": ("qa/**",),
}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(folder: Path) -> dict[str, str]:
    return {
        path.relative_to(folder).as_posix(): _hash_file(path)
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def classify_action(prompt: str) -> str:
    text = prompt.casefold()
    if any(word in text for word in ("翻译", "译文", "中文稿", "术语", "translation")):
        return "translation"
    if any(word in text for word in ("期刊", "模板", "投稿版本", "journal", "format")):
        return "journal"
    if any(word in text for word in ("审稿", "返修", "回复", "review", "revision")):
        return "review"
    if any(word in text for word in ("研究", "证据", "文献", "实验", "引用", "evidence", "citation")):
        return "research"
    return "audit"


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def agent_available(codex_path: str | None = None) -> tuple[bool, str]:
    executable = codex_path or shutil.which("codex")
    if not executable:
        return False, "未找到本机 Codex CLI"
    try:
        result = subprocess.run(
            [executable, "login", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"无法检查 Codex：{exc}"
    if result.returncode != 0:
        return False, "Codex 尚未登录"
    return True, "本机 Codex 已就绪"


class AgentJobManager:
    def __init__(self, root: Path, *, codex_path: str | None = None, execute: bool = True):
        self.root = root.resolve()
        self.jobs_root = self.root / ".paperflow" / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.codex_path = codex_path or shutil.which("codex")
        self.execute = execute
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self.recover_interrupted_jobs()

    def job_dir(self, job_id: str) -> Path:
        if not re_safe_id(job_id):
            raise PaperflowError("无效 Agent 任务编号")
        return self.jobs_root / job_id

    def load(self, job_id: str) -> dict[str, Any]:
        return load_yaml(self.job_dir(job_id) / "job.yaml")

    def list_jobs(self, paper_id: str | None = None) -> list[dict[str, Any]]:
        jobs = []
        for path in sorted(self.jobs_root.glob("*/job.yaml"), reverse=True):
            try:
                job = load_yaml(path)
            except PaperflowError:
                continue
            if paper_id is None or job.get("paper_id") == paper_id:
                jobs.append(job)
        return jobs

    def active_for_paper(self, paper_id: str) -> dict[str, Any] | None:
        return next((job for job in self.list_jobs(paper_id) if job.get("status") in ACTIVE_STATUSES), None)

    def create(self, paper_id: str, prompt: str) -> dict[str, Any]:
        prompt = prompt.strip()
        if not prompt:
            raise PaperflowError("请告诉 Agent 需要完成什么")
        with self._lock:
            if self.active_for_paper(paper_id):
                raise PaperflowError("这篇论文已有 Agent 任务正在运行")
            paper_folder = resolve_paper(self.root, paper_id)
            action = classify_action(prompt)
            job_id = f"J-{now_iso()[:10].replace('-', '')}-{uuid.uuid4().hex[:10]}"
            directory = self.job_dir(job_id)
            workspace_root = directory / "workspace"
            staged_paper = workspace_root / "papers" / paper_folder.name
            staged_paper.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(paper_folder, staged_paper)
            guidance = Path(__file__).resolve().parents[1] / "AGENTS.md"
            if guidance.is_file():
                shutil.copy2(guidance, workspace_root / "AGENTS.md")
            created = now_iso()
            job = {
                "schema_version": "1.0",
                "job_id": job_id,
                "paper_id": paper_id,
                "paper_folder": paper_folder.name,
                "action": action,
                "prompt": prompt,
                "status": "queued",
                "created_at": created,
                "updated_at": created,
                "allowed_outputs": list(ACTION_ALLOWLISTS[action]),
                "forbidden_outputs": list(FORBIDDEN_PATTERNS),
                "baseline_manifest": _manifest(paper_folder),
                "changed_files": [],
                "summary": "等待 Agent 开始",
                "questions": [],
                "checks": [],
                "applied_at": None,
            }
            atomic_yaml(directory / "job.yaml", job)
            self._write_prompt(directory, job)
            if self.execute:
                thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
                thread.start()
            return job

    def _write_prompt(self, directory: Path, job: dict[str, Any]) -> None:
        schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["completed", "needs_user", "failed"]},
                "summary": {"type": "string"},
                "changed_files": {"type": "array", "items": {"type": "string"}},
                "checks": {"type": "array", "items": {"type": "string"}},
                "questions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "summary", "changed_files", "checks", "questions"],
            "additionalProperties": False,
        }
        (directory / "result-schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        prompt = f"""你正在处理 Paperflow 论文副本。只允许在当前工作区内操作。

论文目录：papers/{job['paper_folder']}
用户目标：{job['prompt']}
任务类型：{job['action']}
允许修改：{', '.join(job['allowed_outputs'])}
禁止修改：{', '.join(job['forbidden_outputs'])}

必须遵守：
1. PAPER.yaml、00_source、官方期刊模板和投稿回执不可修改。
2. 不得批准 G0-G5，不得把推测写成已验证科研事实，不得声称翻译或版式已由人确认。
3. 只生成候选内容、检查材料和风险提示；未知信息使用 UNRESOLVED。
4. 修改完成后运行适用的本地检查。不要访问论文目录之外的个人文件。
5. 最终输出必须符合指定 JSON Schema；changed_files 使用相对论文目录的路径。
"""
        (directory / "prompt.md").write_text(prompt, encoding="utf-8")

    def _save(self, job_id: str, job: dict[str, Any]) -> None:
        job["updated_at"] = now_iso()
        atomic_yaml(self.job_dir(job_id) / "job.yaml", job)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self.load(job_id)
            if job.get("status") == "cancelled":
                return
            job["status"] = "running"
            job["summary"] = "Agent 正在隔离副本中处理"
            self._save(job_id, job)
        directory = self.job_dir(job_id)
        if not self.codex_path:
            self._finish_failure(job_id, "未找到本机 Codex CLI")
            return
        command = [
            self.codex_path,
            "-a",
            "never",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-C",
            str(directory / "workspace"),
            "-s",
            "workspace-write",
            "--output-schema",
            str(directory / "result-schema.json"),
            "--output-last-message",
            str(directory / "result.json"),
            "--json",
            "-",
        ]
        try:
            with (directory / "prompt.md").open("r", encoding="utf-8") as prompt_handle, (
                directory / "events.jsonl"
            ).open("w", encoding="utf-8") as stdout_handle, (directory / "stderr.log").open(
                "w", encoding="utf-8"
            ) as stderr_handle:
                process = subprocess.Popen(
                    command,
                    stdin=prompt_handle,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    shell=False,
                )
                with self._lock:
                    self._processes[job_id] = process
                return_code = process.wait()
        except OSError as exc:
            self._finish_failure(job_id, f"无法启动 Agent：{exc}")
            return
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
        job = self.load(job_id)
        if job.get("status") == "cancelled":
            return
        if return_code != 0:
            self._finish_failure(job_id, f"Agent 执行失败，退出码 {return_code}")
            return
        try:
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            self._collect_result(job_id, result)
        except (OSError, json.JSONDecodeError, PaperflowError) as exc:
            self._finish_failure(job_id, f"Agent 结果无法验证：{exc}")

    def _collect_result(self, job_id: str, result: dict[str, Any]) -> None:
        directory = self.job_dir(job_id)
        job = self.load(job_id)
        staged = directory / "workspace" / "papers" / str(job["paper_folder"])
        after = _manifest(staged)
        baseline = dict(job.get("baseline_manifest", {}))
        changed = sorted(path for path, digest in after.items() if baseline.get(path) != digest)
        deleted = sorted(path for path in baseline if path not in after)
        forbidden = [path for path in [*changed, *deleted] if _matches(path, FORBIDDEN_PATTERNS)]
        outside_allowlist = [path for path in changed if not _matches(path, tuple(job["allowed_outputs"]))]
        if deleted:
            raise PaperflowError("Agent 不得删除文件：" + ", ".join(deleted))
        if forbidden:
            raise PaperflowError("Agent 修改了受保护文件：" + ", ".join(forbidden))
        if outside_allowlist:
            raise PaperflowError("Agent 修改超出任务范围：" + ", ".join(outside_allowlist))
        validation: list[str] = []
        for relative in changed:
            path = staged / relative
            if path.suffix.casefold() in {".yaml", ".yml"}:
                load_yaml(path)
                validation.append(f"YAML 可解析：{relative}")
            elif path.suffix.casefold() == ".jsonl":
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if line.strip():
                        try:
                            json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise PaperflowError(f"JSONL 无法解析：{relative}:{number}: {exc}") from exc
                validation.append(f"JSONL 可解析：{relative}")
            elif path.suffix.casefold() == ".docx":
                issues = audit_docx(path)
                validation.extend(f"DOCX {issue.code}：{relative}" for issue in issues)
        staged_issues = check_paper(directory / "workspace" / "papers", str(job["paper_id"]))
        validation.extend(f"Paperflow {issue.code}：{issue.message}" for issue in staged_issues)
        output = directory / "output"
        for relative in changed:
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged / relative, destination)
        status = str(result.get("status", "completed"))
        if status not in {"completed", "needs_user", "failed"}:
            status = "failed"
        job["status"] = status
        job["summary"] = str(result.get("summary", "Agent 已完成处理"))
        job["changed_files"] = changed
        job["checks"] = [*list(result.get("checks", [])), *validation]
        job["questions"] = list(result.get("questions", []))
        self._save(job_id, job)

    def _finish_failure(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self.load(job_id)
            if job.get("status") == "cancelled":
                return
            job["status"] = "failed"
            job["summary"] = message
            self._save(job_id, job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.load(job_id)
            if job.get("status") not in ACTIVE_STATUSES:
                raise PaperflowError("该任务当前不能取消")
            process = self._processes.get(job_id)
            if process is not None and process.poll() is None:
                process.terminate()
            job["status"] = "cancelled"
            job["summary"] = "任务已由用户取消"
            self._save(job_id, job)
            return job

    def retry(self, job_id: str) -> dict[str, Any]:
        old = self.load(job_id)
        if old.get("status") not in {"failed", "cancelled", "needs_user"}:
            raise PaperflowError("该任务当前不能重试")
        return self.create(str(old["paper_id"]), str(old["prompt"]))

    def apply(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.load(job_id)
            if job.get("status") != "completed":
                raise PaperflowError("只有已完成且通过验证的任务可以接受")
            paper_folder = resolve_paper(self.root, str(job["paper_id"]))
            current = _manifest(paper_folder)
            baseline = dict(job.get("baseline_manifest", {}))
            conflicts = [path for path in job.get("changed_files", []) if current.get(path) != baseline.get(path)]
            if conflicts:
                raise PaperflowError("正式论文在 Agent 运行期间已变化：" + ", ".join(conflicts))
            backups = self.job_dir(job_id) / "backups"
            applied: list[str] = []
            try:
                for relative in job.get("changed_files", []):
                    if not _matches(relative, tuple(job["allowed_outputs"])) or _matches(relative, FORBIDDEN_PATTERNS):
                        raise PaperflowError(f"拒绝应用越权文件：{relative}")
                    source = self.job_dir(job_id) / "output" / relative
                    target = paper_folder / relative
                    resolved = target.resolve()
                    if paper_folder.resolve() not in resolved.parents:
                        raise PaperflowError(f"拒绝应用越界路径：{relative}")
                    if target.exists():
                        backup = backups / relative
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(f".{target.name}.{job_id}.tmp")
                    shutil.copy2(source, temporary)
                    os.replace(temporary, target)
                    applied.append(relative)
                rebuild_portfolio(self.root)
            except Exception:
                for relative in reversed(applied):
                    target = paper_folder / relative
                    backup = backups / relative
                    if backup.exists():
                        shutil.copy2(backup, target)
                    else:
                        target.unlink(missing_ok=True)
                rebuild_portfolio(self.root)
                raise
            job["status"] = "applied"
            job["summary"] = f"已接受 {len(applied)} 个 Agent 输出文件"
            job["applied_at"] = now_iso()
            self._save(job_id, job)
            return job

    def recover_interrupted_jobs(self) -> None:
        for job in self.list_jobs():
            if job.get("status") in ACTIVE_STATUSES:
                job["status"] = "failed"
                job["summary"] = "本地服务曾中断；可安全重试此任务"
                self._save(str(job["job_id"]), job)


def re_safe_id(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character in {"-", "_"} for character in value)
