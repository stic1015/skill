from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DraftStore:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, draft_id: str, payload: dict[str, Any]) -> None:
        path = self.root_dir / f"{draft_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, draft_id: str) -> dict[str, Any]:
        path = self.root_dir / f"{draft_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Draft not found: {draft_id}")
        return json.loads(path.read_text(encoding="utf-8"))

