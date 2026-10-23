"""Check Appwrite connectivity, credentials, database, and bucket status."""
from __future__ import annotations

import sys
from .config import settings

def check() -> int:
    print("=" * 60)
    print("Paper2Career - Appwrite Cloud Readiness Check")
    print("=" * 60)

    endpoint = settings.appwrite_endpoint
    project_id = settings.appwrite_project_id
    api_key = settings.appwrite_api_key
    db_id = settings.database_id

    print(f"Endpoint:    {endpoint or '(not set)'}")
    print(f"Project ID:  {project_id or '(not set)'}")
    print(f"API Key:     {'*' * 8 + api_key[-4:] if api_key and len(api_key) > 4 else '(not set)'}")
    print(f"Database ID: {db_id}")
    print("-" * 60)

    if not settings.appwrite_configured:
        print("[!] Appwrite is NOT configured yet.")
        print("    1. Create a project on https://cloud.appwrite.io")
        print("    2. Create a Server API Key in Project Settings -> API Keys")
        print("       (Scopes: databases.*, tables.*, columns.*, indexes.*, rows.*, buckets.*, files.*, teams.*)")
        print("    3. Copy worker/.env.example to worker/.env and fill in the values.")
        print("    4. Copy frontend/.env.example to frontend/.env.local and fill in Endpoint & Project ID.")
        print("=" * 60)
        return 1

    try:
        from appwrite.client import Client
        from appwrite.services.tables_db import TablesDB
        from appwrite.services.storage import Storage
        from appwrite.services.teams import Teams
        from appwrite.exception import AppwriteException
        from .repository import CROPS_BUCKET

        client = Client().set_endpoint(endpoint).set_project(project_id).set_key(api_key)
        tables_db = TablesDB(client)
        storage = Storage(client)
        teams = Storage(client)  # check teams via Teams service
        teams_svc = Teams(client)

        print("[+] Connecting to Appwrite...")
        # Check team
        has_reviewers = False
        try:
            teams_svc.get(team_id="reviewers")
            has_reviewers = True
            print("[+] Team 'reviewers': FOUND")
        except AppwriteException as e:
            if e.code == 404:
                print("[-] Team 'reviewers': NOT FOUND (will be created during setup)")
            else:
                print(f"[!] Team check error ({e.code}): {e.message}")

        # Check database
        has_db = False
        try:
            tables_db.get(database_id=db_id)
            has_db = True
            print(f"[+] Database '{db_id}': FOUND")
        except AppwriteException as e:
            if e.code == 404:
                print(f"[-] Database '{db_id}': NOT FOUND (will be created during setup)")
            else:
                print(f"[!] Database check error ({e.code}): {e.message}")

        # Check tables if DB exists
        if has_db:
            expected_tables = ["editions", "jobs", "job_appearances", "job_revisions", "ingestion_runs"]
            found_tables = []
            for t in expected_tables:
                try:
                    tables_db.get_table(database_id=db_id, table_id=t)
                    found_tables.append(t)
                except AppwriteException:
                    pass
            print(f"[+] Tables: {len(found_tables)}/{len(expected_tables)} present ({', '.join(found_tables) or 'none'})")

        # Check bucket
        has_bucket = False
        try:
            storage.get_bucket(bucket_id=CROPS_BUCKET)
            has_bucket = True
            print(f"[+] Storage bucket '{CROPS_BUCKET}': FOUND")
        except AppwriteException as e:
            if e.code == 404:
                print(f"[-] Storage bucket '{CROPS_BUCKET}': NOT FOUND (will be created during setup)")
            else:
                print(f"[!] Storage bucket error ({e.code}): {e.message}")

        print("-" * 60)
        if not has_db or not has_bucket or not has_reviewers:
            print("[>] NEXT STEP: Run schema setup:")
            print("    python -m paper2career setup")
        else:
            print("[SUCCESS] Appwrite is fully provisioned and ready!")
            print("    * To seed local data & crops into Appwrite:")
            print("      python -m paper2career sync-to-appwrite")
            print("    * To run a daily ingestion directly to Appwrite:")
            print("      python -m paper2career run --auto-publish")
        print("=" * 60)
        return 0

    except Exception as exc:
        print(f"[ERROR] Could not connect to Appwrite: {exc}", file=sys.stderr)
        print("Please check your endpoint, project ID, network connection, and API key scopes.", file=sys.stderr)
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(check())
