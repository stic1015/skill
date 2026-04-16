from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


class GitPublishError(RuntimeError):
    pass


def _run_git(repo: Path, *args: str) -> str:
    cmd = ["git", "-C", str(repo), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitPublishError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")
    return proc.stdout.strip()


def _remote_to_compare_url(remote: str, base: str, branch: str) -> str:
    cleaned = remote.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    https_url = ""
    if cleaned.startswith("git@github.com:"):
        https_url = "https://github.com/" + cleaned.split("git@github.com:", 1)[1]
    elif cleaned.startswith("https://github.com/"):
        https_url = cleaned
    elif cleaned.startswith("http://") or cleaned.startswith("https://"):
        https_url = cleaned

    if https_url:
        return f"{https_url}/compare/{base}...{branch}?expand=1"
    return f"local://{branch}"


class GitPublisher:
    def __init__(self, allow_simulation: bool = True):
        self.allow_simulation = allow_simulation

    def publish(
        self,
        draft: dict[str, Any],
        target_repo: str,
        base_branch: str = "main",
    ) -> dict[str, str]:
        repo = Path(target_repo).resolve()

        spec = draft.get("spec", {})
        name = str(spec.get("name", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,54}", name):
            raise GitPublishError("draft spec.name 非法。")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        branch = f"skillmd/{stamp}-{name[:28]}".rstrip("-")
        rendered_files = draft.get("rendered_files", {})
        if not isinstance(rendered_files, dict) or not rendered_files:
            raise GitPublishError("draft rendered_files 为空。")

        try:
            return self._publish_with_git(
                draft=draft,
                repo=repo,
                base_branch=base_branch,
                branch=branch,
                name=name,
                rendered_files=rendered_files,
            )
        except GitPublishError:
            if not self.allow_simulation:
                raise
            return self._publish_simulated(
                draft=draft,
                repo=repo,
                base_branch=base_branch,
                branch=branch,
                name=name,
                rendered_files=rendered_files,
            )

    def _publish_with_git(
        self,
        draft: dict[str, Any],
        repo: Path,
        base_branch: str,
        branch: str,
        name: str,
        rendered_files: dict[str, Any],
    ) -> dict[str, str]:
        if not (repo / ".git").exists():
            raise GitPublishError(f"target_repo 不是 Git 仓库: {repo}")

        _run_git(repo, "checkout", base_branch)
        _run_git(repo, "checkout", "-b", branch)

        written_paths: list[str] = []
        for rel_path, content in rendered_files.items():
            rel = Path(rel_path)
            abs_path = repo / rel
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(str(content), encoding="utf-8")
            written_paths.append(rel.as_posix())

        for rel in written_paths:
            _run_git(repo, "add", rel)

        commit_message = f"feat(skill): add {name} from skillmd draft {draft.get('draft_id', '')}"
        _run_git(repo, "commit", "-m", commit_message)
        commit_sha = _run_git(repo, "rev-parse", "HEAD")

        remote = ""
        try:
            remote = _run_git(repo, "remote", "get-url", "origin")
        except GitPublishError:
            remote = ""

        pr_url = _remote_to_compare_url(remote=remote, base=base_branch, branch=branch)
        return {
            "pr_url": pr_url,
            "branch": branch,
            "commit_sha": commit_sha,
        }

    def _publish_simulated(
        self,
        draft: dict[str, Any],
        repo: Path,
        base_branch: str,
        branch: str,
        name: str,
        rendered_files: dict[str, Any],
    ) -> dict[str, str]:
        repo.mkdir(parents=True, exist_ok=True)
        for rel_path, content in rendered_files.items():
            rel = Path(rel_path)
            abs_path = repo / rel
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(str(content), encoding="utf-8")

        digest_seed = json.dumps(
            {
                "draft_id": draft.get("draft_id"),
                "name": name,
                "base_branch": base_branch,
                "branch": branch,
                "files": sorted(rendered_files.keys()),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        commit_sha = hashlib.sha1(digest_seed).hexdigest()

        meta_dir = repo / ".skillmd-publish"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / f"{branch.replace('/', '_')}.json").write_text(
            json.dumps(
                {
                    "mode": "simulated",
                    "branch": branch,
                    "commit_sha": commit_sha,
                    "draft_id": draft.get("draft_id"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "pr_url": f"local://draft-pr/{branch}",
            "branch": branch,
            "commit_sha": commit_sha,
        }
