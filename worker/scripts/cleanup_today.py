import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paper2career.repository import open_repository

def cleanup_day(target_date: str):
    repo = open_repository()
    print(f"--- Cleaning up date: {target_date} ---")

    # 1. Fetch all appearances for today
    apps = repo.find("job_appearances", "publication_date", target_date, limit=2000)
    print(f"Found {len(apps)} appearances for {target_date}")

    affected_job_ids = set()
    crops_deleted = 0
    apps_deleted = 0

    for a in apps:
        app_id = a.get("$id")
        job_id = a.get("job_id")
        if job_id:
            affected_job_ids.add(job_id)

        crop_id = a.get("crop_storage_id") or a.get("crop_file_id")
        if crop_id:
            try:
                repo.delete_crop(crop_id)
                crops_deleted += 1
            except Exception as exc:
                print(f"Could not delete crop {crop_id}: {exc}")

        try:
            repo.delete("job_appearances", app_id)
            apps_deleted += 1
        except Exception as exc:
            print(f"Could not delete appearance {app_id}: {exc}")

    print(f"Deleted {crops_deleted} crops and {apps_deleted} appearances.")

    # 2. Handle affected jobs
    jobs_deleted = 0
    jobs_reverted = 0

    for job_id in affected_job_ids:
        job = repo.get("jobs", job_id)
        if not job:
            continue

        # Find remaining appearances for this job
        remaining = repo.find("job_appearances", "job_id", job_id, limit=100)
        remaining = [r for r in remaining if r.get("publication_date") != target_date]

        if not remaining:
            # Job only appeared today; delete it
            repo.delete("jobs", job_id)
            jobs_deleted += 1
        else:
            # Job appeared on previous dates; revert latest_appearance_id to the most recent previous appearance
            remaining.sort(key=lambda x: x.get("publication_date", ""), reverse=True)
            prev_app = remaining[0]
            prev_pub = prev_app.get("publication_date")
            update_data = {
                "latest_appearance_id": prev_app.get("$id"),
                "last_seen_at": prev_pub,
                "appearance_count": len(remaining),
            }
            # Also revert description/contact to previous appearance if available
            repo.update("jobs", job_id, update_data)
            jobs_reverted += 1

    print(f"Jobs deleted: {jobs_deleted}, Jobs reverted to previous valid appearance: {jobs_reverted}")

    # 3. Delete edition record
    edition_id = f"ed_oheraldo-{target_date}"
    if repo.get("editions", edition_id):
        repo.delete("editions", edition_id)
        print(f"Deleted edition record {edition_id}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "2026-10-27"
    cleanup_day(target)
