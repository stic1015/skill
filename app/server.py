from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .git_publisher import GitPublishError
from .models import ModelValidationError
from .service import SkillDraftService


CONVERSATION_SUMMARY_RE = re.compile(r"^/api/conversations/([^/]+)/summary$")
CONVERSATION_CONFIRM_RE = re.compile(r"^/api/conversations/([^/]+)/confirm$")
SKILL_DOWNLOAD_RE = re.compile(r"^/api/skills/([^/]+)/download$")


class SkillMDRequestHandler(BaseHTTPRequestHandler):
    service: SkillDraftService
    static_dir: Path

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/health":
                self._write_json(HTTPStatus.OK, {"status": "ok"})
                return

            if path in {"/", "/index.html"}:
                self._serve_static_index()
                return

            match = CONVERSATION_SUMMARY_RE.match(path)
            if match:
                session_id = unquote(match.group(1))
                response = self.service.get_conversation_summary(session_id)
                self._write_json(HTTPStatus.OK, response)
                return

            match = SKILL_DOWNLOAD_RE.match(path)
            if match:
                draft_id = unquote(match.group(1))
                filename, content = self.service.get_skill_md_download(draft_id)
                self._write_markdown_download(filename=filename, content=content)
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except ModelValidationError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "validation_error", "report": exc.to_dict()})
        except FileNotFoundError as exc:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = self._read_json()

            if path == "/api/conversations/start":
                response = self.service.start_conversation(payload)
                self._write_json(HTTPStatus.OK, response)
                return

            if path == "/api/conversations/answer":
                session_id = payload.get("session_id")
                if not isinstance(session_id, str) or not session_id.strip():
                    raise ModelValidationError(
                        [
                            {
                                "field": "session_id",
                                "message": "session_id is required",
                                "suggestion": "Please send session_id from /api/conversations/start.",
                            }
                        ]
                    )
                response = self.service.answer_conversation(session_id.strip(), payload)
                self._write_json(HTTPStatus.OK, response)
                return

            match = CONVERSATION_CONFIRM_RE.match(path)
            if match:
                session_id = unquote(match.group(1))
                response = self.service.confirm_conversation(session_id, payload)
                self._write_json(HTTPStatus.OK, response)
                return

            if path == "/api/skills/draft":
                response = self.service.create_draft(payload)
                self._write_json(HTTPStatus.OK, response)
                return

            if path == "/api/skills/validate":
                response = self.service.validate(payload)
                self._write_json(HTTPStatus.OK, response)
                return

            if path == "/api/skills/publish-pr":
                response = self.service.publish_pr(payload)
                self._write_json(HTTPStatus.OK, response)
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except ModelValidationError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "validation_error", "report": exc.to_dict()})
        except FileNotFoundError as exc:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except GitPublishError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
        except Exception as exc:  # pragma: no cover
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _serve_static_index(self) -> None:
        index_path = self.static_dir / "index.html"
        if not index_path.exists():
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "index.html not found"})
            return
        body = index_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._write_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length", "0")
        content_len = int(raw_len) if raw_len.isdigit() else 0
        payload = self.rfile.read(content_len) if content_len > 0 else b"{}"
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict):
            raise ModelValidationError(
                [
                    {
                        "field": "payload",
                        "message": "JSON payload must be an object",
                        "suggestion": "Please send a key-value object.",
                    }
                ]
            )
        return data

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._write_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _write_markdown_download(self, filename: str, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self._write_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _write_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def create_server(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    project_root = Path(__file__).resolve().parent.parent
    service = SkillDraftService.from_environment(base_dir=project_root)

    handler_cls = type(
        "ConfiguredSkillMDRequestHandler",
        (SkillMDRequestHandler,),
        {
            "service": service,
            "static_dir": project_root / "app" / "static",
        },
    )
    return ThreadingHTTPServer((host, port), handler_cls)
