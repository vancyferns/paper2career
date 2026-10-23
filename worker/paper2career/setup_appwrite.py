"""Create the Paper2Career database, tables, columns, indexes and reviewers team. Safe to re-run.

API key scopes needed: databases.read/write, tables.read/write, columns.read/write, indexes.read/write,
rows.read/write, teams.read/write, buckets.read/write, files.read/write.

Permission model:
  * Table level: only team:reviewers may read/update (the worker's API key bypasses permissions).
  * Row security ON for jobs/appearances: a row becomes publicly readable only when it is published,
    by adding read("any") to that row. Nobody but the API key and reviewers can write.
"""
from __future__ import annotations

import logging
import time

from .config import settings

log = logging.getLogger(__name__)

S, TEXT = 255, 10000
LONG_TEXT = 2000  # string columns longer than this are created as TEXT
# (key, type, size, required, array)
SCHEMA: dict[str, dict] = {
    "editions": {
        "name": "Editions", "row_security": False,
        "columns": [
            ("edition_key", "string", 64, True, False), ("newspaper", "string", 100, True, False),
            ("publication_date", "string", 10, True, False), ("source_url", "string", 2000, True, False),
            ("source_edition_id", "string", 32, False, False), ("page_count", "integer", None, False, False),
            ("status", "string", 30, True, False), ("classified_pages", "integer", None, False, True),
            ("checksum", "string", 64, False, False), ("jobs_found", "integer", None, False, False),
            ("processed_at", "string", 30, False, False),
        ],
        "indexes": [("idx_pubdate", "key", ["publication_date"])],
    },
    "jobs": {
        "name": "Jobs", "row_security": True,
        "columns": [
            ("title", "string", S, True, False), ("employer", "string", S, False, False),
            ("description", "string", TEXT, True, False), ("location", "string", S, False, False),
            ("qualification", "string", 500, False, False), ("experience", "string", S, False, False),
            ("salary_text", "string", S, False, False), ("contact_phones", "string", 20, False, True),
            ("contact_emails", "string", 254, False, True),
            ("application_instructions", "string", 1000, False, False), ("deadline", "string", 10, False, False),
            ("newspaper", "string", 100, True, False), ("first_seen_at", "string", 10, True, False),
            ("last_seen_at", "string", 10, True, False), ("appearance_count", "integer", None, True, False),
            ("review_status", "string", 30, True, False), ("confidence", "float", None, False, False),
            ("uncertain_fields", "string", 40, False, True), ("has_pending_revision", "boolean", None, False, False),
            ("latest_appearance_id", "string", 36, False, False), ("search_text", "string", 5000, False, False),
            ("reviewed_by", "string", S, False, False), ("reviewed_at", "string", 30, False, False),
        ],
        "indexes": [
            ("idx_status_seen", "key", ["review_status", "last_seen_at"]),
            ("idx_last_seen", "key", ["last_seen_at"]),
            ("idx_location", "key", ["location"]),
            ("idx_search", "fulltext", ["search_text"]),
        ],
    },
    "job_appearances": {
        "name": "Job appearances", "row_security": True,
        "columns": [
            ("job_id", "string", 36, True, False), ("edition_key", "string", 64, True, False),
            ("publication_date", "string", 10, True, False), ("newspaper", "string", 100, True, False),
            ("page_number", "integer", None, True, False), ("ad_reference", "string", 64, False, False),
            ("section", "string", 64, False, False), ("extracted_text", "string", TEXT, True, False),
            ("content_hash", "string", 64, True, False), ("role_index", "integer", None, False, False),
            ("confidence", "float", None, False, False), ("match_type", "string", 20, True, False),
            ("match_score", "float", None, False, False), ("source_url", "string", 2000, True, False),
            ("page_image_url", "string", 2000, False, False), ("bbox", "integer", None, False, True),
            ("page_width", "integer", None, False, False), ("page_height", "integer", None, False, False),
            ("crop_file_id", "string", 36, False, False),
        ],
        "indexes": [
            ("idx_job", "key", ["job_id", "publication_date"]),
            ("idx_hash", "key", ["content_hash"]),
        ],
    },
    "job_revisions": {
        "name": "Job revisions", "row_security": False,
        "columns": [
            ("job_id", "string", 36, True, False), ("appearance_id", "string", 36, True, False),
            ("publication_date", "string", 10, True, False), ("match_type", "string", 20, True, False),
            ("match_score", "float", None, False, False), ("status", "string", 20, True, False),
            ("changed_fields", "string", 40, False, True), ("old_values", "string", 5000, False, False),
            ("new_values", "string", 5000, False, False), ("created_at", "string", 30, True, False),
            ("resolved_by", "string", S, False, False), ("resolved_at", "string", 30, False, False),
        ],
        "indexes": [("idx_status", "key", ["status"]), ("idx_job", "key", ["job_id"])],
    },
    "ingestion_runs": {
        "name": "Ingestion runs", "row_security": False, "public_read": True,
        "columns": [
            ("started_at", "string", 30, True, False), ("finished_at", "string", 30, False, False),
            ("status", "string", 20, True, False), ("trigger", "string", 20, False, False),
            ("editions_checked", "integer", None, False, False), ("editions_found", "integer", None, False, False),
            ("editions_processed", "integer", None, False, False), ("pages_processed", "integer", None, False, False),
            ("pages_failed", "integer", None, False, False), ("ads_found", "integer", None, False, False),
            ("jobs_extracted", "integer", None, False, False), ("new_jobs", "integer", None, False, False),
            ("repeat_appearances", "integer", None, False, False), ("revisions_flagged", "integer", None, False, False),
            ("skipped_existing", "integer", None, False, False), ("error_message", "string", 5000, False, False),
            ("notes", "string", 5000, False, False),
        ],
        "indexes": [("idx_started", "key", ["started_at"])],
    },
}


def setup() -> None:
    from appwrite.client import Client
    from appwrite.enums.tables_db_index_type import TablesDBIndexType as IndexType
    from appwrite.exception import AppwriteException
    from appwrite.permission import Permission
    from appwrite.role import Role
    from appwrite.services.tables_db import TablesDB
    from appwrite.services.storage import Storage
    from appwrite.services.teams import Teams

    from .repository import CROPS_BUCKET

    if not settings.appwrite_configured:
        raise SystemExit("Set APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID and APPWRITE_API_KEY first (see .env.example)")

    client = Client().set_endpoint(settings.appwrite_endpoint).set_project(settings.appwrite_project_id) \
        .set_key(settings.appwrite_api_key)
    db, teams, storage = TablesDB(client), Teams(client), Storage(client)
    dbid = settings.database_id

    def exists(call) -> bool:
        try:
            call()
            return True
        except AppwriteException as exc:
            if exc.code == 404:
                return False
            raise

    if not exists(lambda: teams.get(team_id="reviewers")):
        teams.create(team_id="reviewers", name="Reviewers")
        log.info("Created team 'reviewers' - invite admin users to it from the Appwrite console")

    if not exists(lambda: db.get(database_id=dbid)):
        try:
            db.create(database_id=dbid, name="Paper2Career")
            log.info("Created database %s", dbid)
        except AppwriteException as exc:
            if "maximum number of databases" in str(exc).lower() or exc.code == 400:
                print("\n" + "=" * 60)
                print("ERROR: Appwrite free plan allows only 1 database.")
                print(f"A database already exists but its ID is not '{dbid}'.")
                print("\nFix - pick one option:")
                print("  A) Appwrite Console -> Databases -> delete the existing")
                print(f"     database, then re-run:  python -m paper2career setup")
                print("  B) Copy the existing Database ID from the Appwrite Console,")
                print("     update APPWRITE_DATABASE_ID in worker/.env and")
                print("     VITE_APPWRITE_DATABASE_ID in frontend/.env.local,")
                print(f"     then re-run:  python -m paper2career setup")
                print("=" * 60 + "\n")
                raise SystemExit(1)
            raise
    else:
        log.info("Database '%s' already exists - skipping creation", dbid)

    reviewers = Role.team("reviewers")
    if not exists(lambda: storage.get_bucket(bucket_id=CROPS_BUCKET)):
        # File security on: each crop becomes public only when its job is published.
        storage.create_bucket(bucket_id=CROPS_BUCKET, name="Ad crops", permissions=[Permission.read(reviewers)],
                              file_security=True, maximum_file_size=2_000_000, allowed_file_extensions=["jpg"])
        log.info("Created storage bucket %s", CROPS_BUCKET)
    for table_id, spec in SCHEMA.items():
        perms = [Permission.read(reviewers), Permission.update(reviewers)]
        if spec.get("public_read"):
            perms.append(Permission.read(Role.any()))
        if exists(lambda: db.get_table(database_id=dbid, table_id=table_id)):
            db.update_table(database_id=dbid, table_id=table_id, name=spec["name"], permissions=perms,
                            row_security=spec["row_security"])
        else:
            db.create_table(database_id=dbid, table_id=table_id, name=spec["name"], permissions=perms,
                            row_security=spec["row_security"])
            log.info("Created table %s", table_id)

        current = _as_dict(db.list_columns(database_id=dbid, table_id=table_id))
        have = {c["key"] for c in current.get("columns", [])}
        for key, kind, size, required, array in spec["columns"]:
            if key in have:
                continue
            common = dict(database_id=dbid, table_id=table_id, key=key, required=required, array=array)
            if kind == "string" and size > LONG_TEXT:
                db.create_text_column(**common)        # TEXT doesn't count toward MariaDB's 64 KB row limit
            elif kind == "string":
                db.create_varchar_column(size=size, **common)
            elif kind == "integer":
                db.create_integer_column(**common)
            elif kind == "float":
                db.create_float_column(**common)
            elif kind == "boolean":
                db.create_boolean_column(**common)
            log.info("  + %s.%s (%s)", table_id, key, kind)

        _wait_for_columns(db, dbid, table_id)
        have_idx = {i["key"] for i in _as_dict(db.list_indexes(database_id=dbid, table_id=table_id)).get("indexes", [])}
        for key, kind, cols in spec["indexes"]:
            if key not in have_idx:
                db.create_index(database_id=dbid, table_id=table_id, key=key,
                                type=IndexType.FULLTEXT if kind == "fulltext" else IndexType.KEY, columns=cols)
                log.info("  + index %s.%s", table_id, key)
    log.info("Appwrite setup complete")


def _as_dict(result) -> dict:
    return result if isinstance(result, dict) else result.to_dict()


def _wait_for_columns(db, dbid: str, table_id: str, timeout: float = 120) -> None:
    """Columns are created asynchronously; indexes can only be built once they're available."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cols = _as_dict(db.list_columns(database_id=dbid, table_id=table_id)).get("columns", [])
        pending = [c["key"] for c in cols if c.get("status") != "available"]
        failed = [c["key"] for c in cols if c.get("status") == "failed"]
        if failed:
            raise RuntimeError(f"Column creation failed on {table_id}: {failed}")
        if not pending:
            return
        time.sleep(2)
    raise TimeoutError(f"Columns on {table_id} still processing after {timeout}s")
