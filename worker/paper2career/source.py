"""O Heraldo e-paper adapter: discover editions and acquire page images.

Verified against the live site (Oct 2026):
  * /epaper/oheraldo/DD-MM-YYYY           -> edition page (HTML)
  * edition page lists every page as      <a data-ed_date="YYYY-MM-DD" data-page="N" data-id="<edition id>">
  * the page image is                     /uploads/epaper/YYYY-MM/<hash>.jpg
    (the HTML references thumbnail-150-/thumbnail-800- variants; stripping the prefix gives full resolution)
  * /epaper/oheraldo/<id>/page/N with X-Requested-With returns JSON whose `ajax1` holds that page's image
  * robots.txt disallows only /admin/.

There is no public PDF link, so pages are acquired as images and OCR'd. We do not log in or work
around any access control; if the layout changes, discovery fails loudly and the run is logged as FAILED.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:
    from curl_cffi import requests
    _CURL_CFFI = True
except ImportError:
    import requests
    _CURL_CFFI = False
from bs4 import BeautifulSoup

from .config import settings

log = logging.getLogger(__name__)

_IMG_RE = re.compile(r"/uploads/epaper/(\d{4}-\d{2})/(?:thumbnail-\d+-)?([0-9a-f]{8,})\.jpg", re.I)


class SourceUnavailable(Exception):
    """The source could not be reached or did not look like an e-paper edition."""


class LayoutChanged(Exception):
    """The source responded, but its HTML no longer matches what this adapter expects."""


@dataclass
class PageRef:
    page_number: int
    viewer_url: str
    image_url: str
    preview_url: str = ""     # ~800 px wide copy, enough to recognise the classifieds page cheaply


@dataclass
class EditionRef:
    publication_date: date
    edition_key: str          # e.g. "oheraldo-2026-10-23"
    source_edition_id: str    # site's numeric id
    source_url: str
    pages: list[PageRef]


@dataclass
class AcquiredPage:
    page: PageRef
    path: Path
    checksum: str


class HeraldoSource:
    def __init__(self, session=None):
        self.base = settings.source_base_url
        self.alias = settings.source_alias
        if session is not None:
            self.session = session
        elif _CURL_CFFI:
            self.session = requests.Session(impersonate="chrome120")
        else:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            })
        self._last_request = 0.0

    def _get(self, url: str, **kwargs) -> requests.Response:
        for attempt in range(1, 4):
            wait = settings.request_delay_seconds - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, timeout=60, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                # Dropped connections happen on large page images; back off and retry the same request.
                if attempt == 3:
                    raise SourceUnavailable(f"GET {url} failed after 3 attempts: {exc}") from exc
                log.warning("GET %s failed (%s); retrying", url, type(exc).__name__)
                time.sleep(5 * attempt)
                continue
            except requests.RequestException as exc:
                raise SourceUnavailable(f"GET {url} failed: {exc}") from exc
            finally:
                self._last_request = time.monotonic()
            if resp.status_code >= 500 and attempt < 3:
                log.warning("GET %s returned %s; retrying", url, resp.status_code)
                time.sleep(5 * attempt)
                continue
            break
        if resp.status_code in (401, 403):
            # Treat as "not permitted" and stop; never retry with a disguised client.
            raise SourceUnavailable(f"GET {url} returned {resp.status_code} (access refused)")
        if resp.status_code == 404:
            return resp
        if resp.status_code >= 400:
            raise SourceUnavailable(f"GET {url} returned {resp.status_code}")
        return resp

    def edition_url(self, day: date) -> str:
        return f"{self.base}/epaper/{self.alias}/{day:%d-%m-%Y}"

    def find_edition(self, day: date) -> EditionRef | None:
        """Return the edition published on `day`, or None if it isn't available (yet)."""
        url = self.edition_url(day)
        resp = self._get(url)
        if resp.status_code == 404:
            return None
        return parse_edition_html(resp.text, day, url, self.base, self.alias)

    def download_page(self, page: PageRef, edition_key: str) -> AcquiredPage:
        path = self._fetch_image(page.image_url, edition_key, f"page-{page.page_number:02d}.jpg")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        return AcquiredPage(page=page, path=path, checksum=checksum)

    def download_preview(self, page: PageRef, edition_key: str) -> Path:
        return self._fetch_image(page.preview_url or page.image_url, edition_key, f"preview-{page.page_number:02d}.jpg")

    def _fetch_image(self, url: str, edition_key: str, name: str) -> Path:
        target_dir = settings.download_dir / edition_key
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name
        if not path.exists():
            resp = self._get(url)
            if resp.status_code != 200 or not resp.headers.get("Content-Type", "").startswith("image"):
                raise SourceUnavailable(f"Image {url} not available ({resp.status_code})")
            path.write_bytes(resp.content)
        return path


def parse_edition_html(html: str, day: date, url: str, base: str, alias: str) -> EditionRef | None:
    soup = BeautifulSoup(html, "html.parser")
    iso = day.isoformat()
    anchors = soup.select(f'a.pagethumb[data-ed_date="{iso}"][data-page]')
    if not anchors:
        # The site serves the latest edition for unknown dates on some paths; make sure we got the right day.
        if soup.select("a.pagethumb[data-ed_date]"):
            return None
        raise LayoutChanged(f"No page thumbnails found on {url}; the e-paper layout may have changed")

    edition_id = ""
    pages: dict[int, PageRef] = {}
    for a in anchors:
        num = int(a["data-page"])
        img = a.find("img")
        match = _IMG_RE.search(img.get("src", "")) if img else None
        if not match:
            continue
        month, image_hash = match.groups()
        pages[num] = PageRef(
            page_number=num,
            viewer_url=f"{base}/epaper/{alias}/{iso}/page/{num}",
            image_url=f"{base}/uploads/epaper/{month}/{image_hash}.jpg",
            preview_url=f"{base}/uploads/epaper/{month}/thumbnail-800-{image_hash}.jpg",
        )
        edition_id = edition_id or a.get("data-id", "")

    if not edition_id:
        m = re.search(rf"/epaper/{re.escape(alias)}/(\d+)/page/\d+", html)
        edition_id = m.group(1) if m else ""
    if not pages:
        raise LayoutChanged(f"Page thumbnails on {url} had no recognisable image URLs")

    return EditionRef(
        publication_date=day,
        edition_key=f"{alias}-{iso}",
        source_edition_id=edition_id,
        source_url=url,
        pages=[pages[n] for n in sorted(pages)],
    )
