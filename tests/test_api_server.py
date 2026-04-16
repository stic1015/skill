from __future__ import annotations

import json
import os
import shutil
import threading
import unittest
import uuid
from pathlib import Path
from urllib import request

from app.server import create_server


class SkillMDApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = Path("D:/Codex/tmp_pycache/skillmd-api-tests")
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.case_dir = self.tmp_root / f"case-{uuid.uuid4().hex[:8]}"
        self.case_dir.mkdir(parents=True, exist_ok=True)

        self.old_env = {
            "SKILLMD_DRAFT_DIR": os.environ.get("SKILLMD_DRAFT_DIR"),
            "SKILLMD_SESSION_DIR": os.environ.get("SKILLMD_SESSION_DIR"),
            "SKILLMD_REGISTRY_PATH": os.environ.get("SKILLMD_REGISTRY_PATH"),
            "SKILLMD_CONVERSATION_STRICT": os.environ.get("SKILLMD_CONVERSATION_STRICT"),
        }
        os.environ["SKILLMD_DRAFT_DIR"] = str(self.case_dir / "drafts")
        os.environ["SKILLMD_SESSION_DIR"] = str(self.case_dir / "sessions")
        os.environ["SKILLMD_REGISTRY_PATH"] = str(self.case_dir / "registry")
        os.environ["SKILLMD_CONVERSATION_STRICT"] = "0"

        self.server = create_server(host="127.0.0.1", port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        shutil.rmtree(self.case_dir, ignore_errors=True)

        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return int(resp.status), data

    def test_download_endpoint_returns_markdown_attachment(self) -> None:
        status, started = self._post_json("/api/conversations/start", {"language": "zh-CN"})
        self.assertEqual(200, status)
        session_id = started["session_id"]

        answers = [
            "沉淀售前答疑流程",
            "售前答疑,客户异议处理",
            "帮我写一段客户回复,客户预算不够怎么回",
            "产品资料,历史案例",
            "结构化回复草稿,行动建议",
            "仅基于已知资料",
            "法律建议,医疗建议",
            "客户嫌贵怎么回应",
        ]
        for answer in answers:
            status, _ = self._post_json("/api/conversations/answer", {"session_id": session_id, "answer": answer})
            self.assertEqual(200, status)

        status, confirmed = self._post_json(f"/api/conversations/{session_id}/confirm", {"confirmed": True})
        self.assertEqual(200, status)
        draft_id = confirmed["draft_id"]

        with request.urlopen(self._url(f"/api/skills/{draft_id}/download"), timeout=10) as resp:
            body = resp.read().decode("utf-8")
            disposition = resp.headers.get("Content-Disposition", "")
            content_type = resp.headers.get("Content-Type", "")
            self.assertEqual(200, int(resp.status))
            self.assertIn("attachment; filename=", disposition)
            self.assertIn("text/markdown", content_type)
            self.assertIn("## Overview", body)


if __name__ == "__main__":
    unittest.main()
