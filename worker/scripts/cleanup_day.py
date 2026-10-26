import sys
from paper2career.repository import open_repository

def cleanup_day(target_date: str = "2026-10-26"):
    repo = open_repository()
    apps = repo.find("job_appearances", "publication_date", target_date, limit=2000)
    print(f"Found {len(apps)} appearances for {target_date}")

    job_ids = set()
    crop_ids = set()
    for a in apps:
        job_ids.add(a["job_id"])
        if a.get("crop_file_id"):
            crop_ids.add(a["crop_file_id"])
        repo.delete("job_appearances", a["$id"])

    print(f"Deleted {len(apps)} job appearances")

    deleted_crops = 0
    for cid in crop_ids:
        try:
            repo.delete_crop(cid)
            deleted_crops += 1
        except Exception:
            pass
    print(f"Deleted {deleted_crops} crop files from storage")

    deleted_jobs = 0
    updated_jobs = 0
    for jid in job_ids:
        other_apps = repo.find("job_appearances", "job_id", jid, limit=100)
        if not other_apps:
            repo.delete("jobs", jid)
            deleted_jobs += 1
        else:
            latest_date = max(a["publication_date"] for a in other_apps)
            latest_app_id = next(a["$id"] for a in other_apps if a["publication_date"] == latest_date)
            repo.update("jobs", jid, {
                "last_seen_at": latest_date,
                "appearance_count": len(other_apps),
                "latest_appearance_id": latest_app_id,
            })
            updated_jobs += 1

    print(f"Deleted {deleted_jobs} single-day jobs, reverted {updated_jobs} multi-day jobs")

    ed_id = f"ed_oheraldo-{target_date}"
    repo.delete("editions", ed_id)
    print(f"Deleted edition {ed_id}")
    print("Cleanup complete!")

if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else "2026-10-26"
    cleanup_day(date_arg)
