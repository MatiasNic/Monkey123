"""Persistencia en archivos del repo: historial (jsonl), cola y banco de ideas (yaml)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

STATES = ("draft", "approved", "queued", "published", "discarded")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class History:
    """data/history.jsonl: una línea por pieza. Las actualizaciones reescriben el archivo."""

    def __init__(self, path: Path):
        self.path = path

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def recent(self, n: int) -> list[dict]:
        items = [r for r in self.all() if r.get("status") != "discarded"]
        return items[-n:]

    def append(self, records: list[dict]) -> None:
        with self.path.open("a") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def update(self, item_id: str, **fields) -> dict:
        records = self.all()
        for rec in records:
            if rec["id"] == item_id:
                rec.update(fields, updated_at=now_iso())
                break
        else:
            raise KeyError(item_id)
        self._write(records)
        return rec

    def get(self, item_id: str) -> dict:
        for rec in self.all():
            if rec["id"] == item_id:
                return rec
        raise KeyError(item_id)

    def _write(self, records: list[dict]) -> None:
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))


class YamlDoc:
    def __init__(self, path: Path, key: str):
        self.path, self.key = path, key

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return (yaml.safe_load(self.path.read_text()) or {}).get(self.key) or []

    def save(self, items: list[dict], header: str = "") -> None:
        body = yaml.safe_dump({self.key: items}, allow_unicode=True, sort_keys=False, width=120)
        self.path.write_text(header + body)


class IdeaBank(YamlDoc):
    HEADER = "# Banco de ideas. Claude lo amplía en cada tanda y va consumiendo conceptos (used: true).\n"

    def __init__(self, path: Path):
        super().__init__(path, "ideas")

    def unused(self) -> list[str]:
        return [i["concept"] for i in self.load() if not i.get("used")]

    def mark_used(self, concepts: list[str]) -> None:
        items = self.load()
        for item in items:
            if item["concept"] in concepts:
                item["used"] = True
        self.save(items, self.HEADER)

    def extend(self, concepts: list[str]) -> None:
        items = self.load()
        known = {i["concept"].lower() for i in items}
        items += [{"concept": c, "used": False} for c in concepts if c and c.lower() not in known]
        self.save(items, self.HEADER)


class Queue(YamlDoc):
    HEADER = "# Cola de publicación. La llena `mono approve` al mergear un PR de tanda.\n"

    def __init__(self, path: Path):
        super().__init__(path, "items")
