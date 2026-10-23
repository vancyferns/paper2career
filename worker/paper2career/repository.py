"""Persistence. AppwriteRepository is the real store; LocalRepository is a JSON file for offline runs and tests.

Both expose the same small interface so the pipeline never touches SDK details.
Row ids are deterministic (derived from edition + content hash), which is what makes re-runs idempotent.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TABLES = ("editions", "jobs", "job_appearances", "job_revisions", "ingestion_runs")
CROPS_BUCKET = "ad_crops"


class Repository:
    def get(self, table: str, row_id: str) -> dict | None: ...
    def create(self, table: str, row_id: str, data: dict, public: bool = False) -> dict: ...
    def update(self, table: str, row_id: str, data: dict, public: bool | None = None) -> dict: ...
    def find(self, table: str, field: str, value: Any, limit: int = 100) -> list[dict]: ...
    def find_since(self, table: str, field: str, since: str, limit: int = 1000) -> list[dict]: ...
    def all(self, table: str, limit: int = 5000) -> list[dict]: ...
    def delete(self, table: str, row_id: str) -> bool: ...
    def save_crop(self, file_id: str, jpeg: bytes, public: bool = False) -> str | None:
        """Store an ad's evidence image. Returns a file id."""
    def delete_crop(self, file_id: str) -> bool:
        """Delete an ad's evidence image from storage."""

    def upsert(self, table: str, row_id: str, data: dict, public: bool | None = None) -> dict:
        if self.get(table, row_id) is None:
            return self.create(table, row_id, data, public=bool(public))
        return self.update(table, row_id, data, public=public)


# ---------------------------------------------------------------- local JSON

class LocalRepository(Repository):
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict[str, dict]] = {t: {} for t in TABLES}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            for t in TABLES:
                self.data[t] = loaded.get(t, {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, table, row_id):
        row = self.data[table].get(row_id)
        return dict(row) if row else None

    def create(self, table, row_id, data, public=False):
        if row_id in self.data[table]:
            raise KeyError(f"{table}/{row_id} already exists")
        row = {"$id": row_id, **data, "$public": public}
        self.data[table][row_id] = row
        self._save()
        return dict(row)

    def update(self, table, row_id, data, public=None):
        row = self.data[table][row_id]
        row.update(data)
        if public is not None:
            row["$public"] = public
        self._save()
        return dict(row)

    def find(self, table, field, value, limit=100):
        out = []
        for row in self.data[table].values():
            v = row.get(field)
            if v == value or (isinstance(v, list) and value in v):
                out.append(dict(row))
        return out[:limit]

    def find_since(self, table, field, since, limit=1000):
        return [dict(r) for r in self.data[table].values() if (r.get(field) or "") >= since][:limit]

    def all(self, table, limit=5000):
        return [dict(r) for r in list(self.data[table].values())[:limit]]

    def delete(self, table, row_id):
        if row_id in self.data[table]:
            del self.data[table][row_id]
            self._save()
            return True
        return False

    def save_crop(self, file_id, jpeg, public=False):
        crops = self.path.parent / "crops"
        crops.mkdir(parents=True, exist_ok=True)
        (crops / f"{file_id}.jpg").write_bytes(jpeg)
        return file_id

    def delete_crop(self, file_id):
        crops = self.path.parent / "crops"
        crop_file = crops / f"{file_id}.jpg"
        if crop_file.exists():
            crop_file.unlink()
            return True
        return False


# ---------------------------------------------------------------- Appwrite TablesDB

class AppwriteRepository(Repository):
    """Server-side access with an API key. Never use this key in the browser."""

    REVIEWERS = "team:reviewers"

    def __init__(self, endpoint: str, project_id: str, api_key: str, database_id: str):
        from appwrite.client import Client
        from appwrite.services.tables_db import TablesDB

        from appwrite.services.storage import Storage

        client = Client().set_endpoint(endpoint).set_project(project_id).set_key(api_key)
        self.db = TablesDB(client)
        self.storage = Storage(client)
        self.database_id = database_id

    def _perms(self, public: bool) -> list[str]:
        from appwrite.permission import Permission
        from appwrite.role import Role

        perms = [Permission.read(Role.team("reviewers")), Permission.update(Role.team("reviewers"))]
        if public:
            perms.append(Permission.read(Role.any()))
        return perms

    @staticmethod
    def _row(result) -> dict:
        row = result if isinstance(result, dict) else result.to_dict()
        data = dict(row.get("data") or {})
        data.update({k: v for k, v in row.items() if k != "data"})
        perms = row.get("$permissions") or []
        data["$public"] = any(p.startswith('read("any")') for p in perms)
        return data

    def get(self, table, row_id):
        from appwrite.exception import AppwriteException

        try:
            return self._row(self.db.get_row(database_id=self.database_id, table_id=table, row_id=row_id))
        except AppwriteException as exc:
            if exc.code == 404:
                return None
            raise

    def create(self, table, row_id, data, public=False):
        clean_data = {k: v for k, v in data.items() if not k.startswith("$")}
        return self._row(self.db.create_row(
            database_id=self.database_id, table_id=table, row_id=row_id, data=clean_data,
            permissions=self._perms(public),
        ))

    def update(self, table, row_id, data, public=None):
        clean_data = {k: v for k, v in data.items() if not k.startswith("$")}
        kwargs = {"permissions": self._perms(public)} if public is not None else {}
        return self._row(self.db.update_row(
            database_id=self.database_id, table_id=table, row_id=row_id, data=clean_data, **kwargs,
        ))

    def _list(self, table, queries, limit):
        from appwrite.query import Query

        rows, cursor = [], None
        while len(rows) < limit:
            page_size = min(100, limit - len(rows))
            q = [*queries, Query.limit(page_size)]
            if cursor:
                q.append(Query.cursor_after(cursor))
            res = self.db.list_rows(database_id=self.database_id, table_id=table, queries=q)
            res = res if isinstance(res, dict) else res.to_dict()
            batch = [self._row(r) for r in res.get("rows", [])]
            rows.extend(batch)
            if len(batch) < page_size:
                break
            cursor = batch[-1]["$id"]
        return rows

    def find(self, table, field, value, limit=100):
        from appwrite.query import Query

        q = Query.contains(field, [value]) if isinstance(value, str) and field.endswith("_phones") else Query.equal(field, [value])
        return self._list(table, [q], limit)

    def find_since(self, table, field, since, limit=1000):
        from appwrite.query import Query

        return self._list(table, [Query.greater_than_equal(field, since)], limit)

    def all(self, table, limit=5000):
        return self._list(table, [], limit)

    def delete(self, table, row_id):
        from appwrite.exception import AppwriteException

        try:
            self.db.delete_row(database_id=self.database_id, table_id=table, row_id=row_id)
            return True
        except AppwriteException as exc:
            if exc.code == 404:
                return False
            raise

    def save_crop(self, file_id, jpeg, public=False):
        from appwrite.exception import AppwriteException
        from appwrite.input_file import InputFile

        try:
            self.storage.create_file(bucket_id=CROPS_BUCKET, file_id=file_id,
                                     file=InputFile.from_bytes(jpeg, f"{file_id}.jpg", "image/jpeg"),
                                     permissions=self._perms(public))
        except AppwriteException as exc:
            if exc.code != 409:      # already uploaded by an earlier run
                raise
        return file_id

    def delete_crop(self, file_id):
        from appwrite.exception import AppwriteException

        try:
            self.storage.delete_file(bucket_id=CROPS_BUCKET, file_id=file_id)
            return True
        except AppwriteException as exc:
            if exc.code == 404:
                return False
            raise


def open_repository(local_path: Path | None = None) -> Repository:
    from .config import settings

    if local_path is None and settings.appwrite_configured:
        log.info("Using Appwrite database %s at %s", settings.database_id, settings.appwrite_endpoint)
        return AppwriteRepository(settings.appwrite_endpoint, settings.appwrite_project_id,
                                  settings.appwrite_api_key, settings.database_id)
    path = local_path or (Path(__file__).resolve().parent.parent / "data" / "local_db.json")
    log.warning("Appwrite not configured; using local store %s", path)
    return LocalRepository(path)
