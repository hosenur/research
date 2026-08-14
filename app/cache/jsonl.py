from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlCache:
    """Append-only JSONL cache. Same get/set shape a Redis wrapper can take later."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = record.get("key")
            if isinstance(key, str):
                self._data[key] = record.get("value")

    def get(self, key: str) -> Any | None:
        if key not in self._data:
            return None
        return self._data[key]

    def items(self) -> list[tuple[str, Any]]:
        """Return the latest value for every legacy key for an idempotent DB backfill."""
        return list(self._data.items())

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
