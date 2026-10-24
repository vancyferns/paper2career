"""Runtime configuration, read from environment variables (or a local .env file)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so local runs don't need an extra dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    appwrite_endpoint: str = field(default_factory=lambda: os.environ.get("APPWRITE_ENDPOINT", "").rstrip("/"))
    appwrite_project_id: str = field(default_factory=lambda: os.environ.get("APPWRITE_PROJECT_ID", ""))
    appwrite_api_key: str = field(default_factory=lambda: os.environ.get("APPWRITE_API_KEY", ""))
    database_id: str = field(default_factory=lambda: os.environ.get("APPWRITE_DATABASE_ID", "6adbb053000fa129e183"))

    source_base_url: str = "https://epaper.heraldgoa.in"
    source_alias: str = field(default_factory=lambda: os.environ.get("SOURCE_ALIAS", "oheraldo"))
    newspaper_name: str = "O Heraldo"
    user_agent: str = "Paper2Career/0.1 (+newspaper job discovery; respects robots.txt)"
    request_delay_seconds: float = float(os.environ.get("REQUEST_DELAY_SECONDS", "1.5"))

    # How many days back to look for unprocessed editions on each run.
    lookback_days: int = int(os.environ.get("LOOKBACK_DAYS", "3"))
    download_dir: Path = Path(os.environ.get("DOWNLOAD_DIR", Path(__file__).resolve().parent.parent / "downloads"))

    # Records below this extraction confidence are always held for review.
    review_confidence_threshold: float = float(os.environ.get("REVIEW_CONFIDENCE_THRESHOLD", "0.75"))

    # When true, newly extracted jobs are automatically published without manual review.
    auto_publish: bool = field(
        default_factory=lambda: os.environ.get("AUTO_PUBLISH", "false").lower() in ("1", "true", "yes")
    )

    @property
    def appwrite_configured(self) -> bool:
        return bool(self.appwrite_endpoint and self.appwrite_project_id and self.appwrite_api_key)


settings = Settings()
