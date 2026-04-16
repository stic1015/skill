from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .git_publisher import GitPublishError
from .models import ModelValidationError
from .service import SkillDraftService


class SkillMDRequestHandler(BaseHTTPRequestHandler):
    service: SkillDraftService
    static_dir: Path

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path in {"/", "/index.html"}:
            index_path = self.static_dir / "index.html"
            if not index_path.exists():
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "index.html not found"})
                return
            body = index_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            if self.path == "/api/skills/draft":
                response = self.service.create_draft(payload)
                self._write_json(HTTPStatus.OK, response)
                return
            if self.path == "/api/skills/validate":
                response = self.service.validate(payload)
                self._write_json(HTTPStatus.OK, response)
                return
            if self.path == "/api/skills/publish-pr":
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
                        "message": "JSON payload 必须是对象",
                        "suggestion": "请传入键值对结构。",
                    }
                ]
            )
        return data

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

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

