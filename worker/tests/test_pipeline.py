"""Acceptance tests from SRS section 8, run against synthetic OCR output and a fake e-paper source."""
from datetime import date
from pathlib import Path

import pytest

from paper2career import extract, pipeline
from paper2career.models import OcrLine
from paper2career.pipeline import Ingestor
from paper2career.repository import LocalRepository
from paper2career.source import EditionRef, PageRef, SourceUnavailable, parse_edition_html

LINE_H = 20


def column(x: int, blocks: list[list[str]], y: int = 0) -> list[OcrLine]:
    """Lay out text blocks top-to-bottom in one column, with a blank gap between blocks."""
    out = []
    for block in blocks:
        for text in block:
            h = LINE_H * 2 if text.isupper() and len(text.split()) <= 3 else LINE_H
            out.append(OcrLine(text, x, y, x + 300, y + h, 0.95))
            y += h + 4
        y += LINE_H * 2
    return out


def classified_page(deadline: str = "30th November 2026") -> list[OcrLine]:
    return column(0, [
        ["SITUATIONS VACANT"],
        ["WANTED Accountant for Sunrise Builders Pvt Ltd,", "Margao. B.Com with Tally, 2 years experience.",
         f"Salary Rs 25,000 p.m. Apply before {deadline}.", "Call 9823012345."],
        ["URGENTLY REQUIRED Driver and Cook for", "family in Porvorim. Contact 9890011223."],
        ["PROPERTY"],
        ["2 BHK flat for sale at Panaji, 1100 sq ft,", "near Miramar. Call 9822000111."],
    ]) + column(400, [
        ["VEHICLES"],
        ["Honda City 2019 model, 40,000 kms driven,", "single owner. Call 9765432100."],
        ["GENERAL"],
        ["WANTED experienced Receptionist for clinic at", "Mapusa. Graduates apply. Ph 9881122334."],
    ])


class FakeSource:
    def __init__(self, editions: dict[date, list[OcrLine] | None], fail: bool = False):
        self.editions = editions
        self.fail = fail

    def edition_url(self, day):
        return f"https://epaper.example/{day}"

    def find_edition(self, day):
        if self.fail:
            raise SourceUnavailable("connection refused")
        if day not in self.editions:
            return None
        key = f"oheraldo-{day.isoformat()}"
        return EditionRef(day, key, "1", self.edition_url(day),
                          [PageRef(4, f"https://epaper.example/{day}/page/4", f"https://img.example/{day}.jpg")])

    def download_preview(self, page, edition_key):
        return Path(f"{edition_key}-preview.jpg")

    def download_page(self, page, edition_key):
        day = date.fromisoformat(edition_key.split("-", 1)[1])
        return pipeline.AcquiredPage(page, Path(f"{edition_key}.jpg"), f"checksum-{day}")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    editions: dict[date, list[OcrLine] | None] = {}
    monkeypatch.setattr(pipeline, "page_lines", lambda path, checksum: editions[date.fromisoformat(checksum[9:])])
    monkeypatch.setattr(pipeline, "_page_size", lambda path: (3000, 4000))
    monkeypatch.setattr(pipeline, "looks_like_classifieds", lambda path: True)
    object.__setattr__(pipeline.settings, "auto_publish", False)
    repo = LocalRepository(tmp_path / "db.json")
    return repo, editions


def jobs(repo):
    return repo.all("jobs")


# ---------------------------------------------------------------- extraction units

def test_category_filtering_excludes_property_and_vehicles():
    ads = extract.segment_ads(classified_page())
    recruitment = [a for a in ads if extract.is_recruitment(a)]
    texts = " ".join(a.text for a in recruitment)
    assert len(recruitment) == 3
    assert "BHK" not in texts and "Honda" not in texts
    assert any("Receptionist" in a.text and a.section == "GENERAL" for a in recruitment)


def test_fields_extracted_and_missing_fields_stay_unknown():
    ads = [a for a in extract.segment_ads(classified_page()) if extract.is_recruitment(a)]
    acct = extract.extract_jobs(ads[0], date(2026, 10, 23))[0]
    assert acct.title == "Accountant"
    assert acct.employer == "Sunrise Builders Pvt Ltd"
    assert acct.location == "Margao"
    assert acct.contact_phones == ["9823012345"]
    assert acct.deadline == "2026-11-30"
    assert "25,000" in acct.salary_text

    driver_cook = extract.extract_jobs(ads[1], date(2026, 10, 23))
    assert [d.title for d in driver_cook] == ["Driver", "Cook"]       # one ad, two vacancies
    assert all(d.salary_text is None and d.deadline is None and d.employer is None for d in driver_cook)


def test_deadline_without_year_rolls_forward():
    ad = extract.segment_ads(column(0, [["SITUATIONS VACANT"], ["WANTED Teacher. Apply before 5th January. Call 9823099999."]]))[0]
    assert extract.extract_jobs(ad, date(2026, 12, 20))[0].deadline == "2027-01-05"


def heraldo_style_page() -> list[OcrLine]:
    """Mimics the real O Heraldo classifieds page: every ad ends in a 10-digit booking number."""
    col1 = column(0, [
        ["PROPERTIES WANTED"],
        ["Wanted 2BHK flat on rent in Porvorim for", "family. Call 9822111000.", "2026207790"],
        ["SITUATIONS VACANT"],
        ["Wanted Driver for goods carrier with", "valid license. Contact 9881100110.", "2026207801"],
        ["Required Accountant for trading firm at", "Verna, B.Com with Tally. Salary", "Rs 20,000. Send CV to"],  # continues
    ])
    col2 = column(400, [
        ["accounts@verna-traders.in or call", "9823456789.", "2026207812"],
        ["Wanted Kitchen Helper and Waiters for", "restaurant at Calangute. 9765012345.", "2026207823"],
        ["Mapusa PIO fined Rs 25k for RTI lapses. The Goa State", "Information Commission fined the officer for",
         "delays in disposing of applications."],
    ])
    for ln in col2:
        if AD_TERMINATOR(ln.text):
            ln.x0 += 200   # booking numbers are right-aligned
    return col1 + col2


def AD_TERMINATOR(text):
    return extract.AD_TERMINATOR_RE.match(text)


def test_reference_numbered_page_segmentation():
    ads = extract.segment_ads(heraldo_style_page())
    jobs_ads = [a for a in ads if extract.is_recruitment(a)]
    refs = [a.ad_reference for a in jobs_ads]
    assert refs == ["2026207801", "2026207812", "2026207823"]
    acct = jobs_ads[1]
    assert acct.text.startswith("Required Accountant") and "9823456789" in acct.text   # joined across columns
    assert "2026207812" not in acct.text
    assert not any("flat on rent" in a.text or "RTI" in a.text for a in jobs_ads)
    titles = [d.title for a in jobs_ads for d in extract.extract_jobs(a, date(2026, 10, 23))]
    assert titles == ["Driver", "Accountant", "Kitchen Helper", "Waiter"]


# ---------------------------------------------------------------- acceptance

def test_rerunning_same_edition_creates_no_duplicates(setup):
    repo, editions = setup
    d = date(2026, 10, 23)
    editions[d] = classified_page()
    first = Ingestor(repo, FakeSource(editions)).run(days=[d])
    assert first["status"] == "SUCCESS" and first["new_jobs"] == 4
    counts = (len(jobs(repo)), len(repo.all("job_appearances")))

    again = Ingestor(repo, FakeSource(editions)).run(days=[d])
    assert again["status"] == "NO_NEW_EDITION"
    forced = Ingestor(repo, FakeSource(editions)).run(days=[d], force=True)
    assert forced["new_jobs"] == 0 and forced["skipped_existing"] == 4
    assert (len(jobs(repo)), len(repo.all("job_appearances"))) == counts


def test_repeated_ad_links_to_existing_job(setup):
    repo, editions = setup
    d1, d2 = date(2026, 10, 23), date(2026, 10, 24)
    editions[d1] = classified_page()
    editions[d2] = classified_page()
    Ingestor(repo, FakeSource(editions)).run(days=[d1, d2])
    assert len(jobs(repo)) == 4
    assert len(repo.all("job_appearances")) == 8
    acct = next(j for j in jobs(repo) if j["title"] == "Accountant")
    assert (acct["first_seen_at"], acct["last_seen_at"], acct["appearance_count"]) == ("2026-10-23", "2026-10-24", 2)
    assert repo.all("job_revisions") == []


def test_repeat_with_ocr_noise_still_matches(setup):
    repo, editions = setup
    d1, d2 = date(2026, 10, 23), date(2026, 10, 24)
    editions[d1] = classified_page()
    noisy = classified_page()
    noisy[1].text = noisy[1].text.replace("Sunrise", "Sunrlse")
    editions[d2] = noisy
    Ingestor(repo, FakeSource(editions)).run(days=[d1, d2])
    assert len(jobs(repo)) == 4


def test_changed_deadline_creates_revision_for_review(setup):
    repo, editions = setup
    d1, d2 = date(2026, 10, 23), date(2026, 10, 25)
    editions[d1] = classified_page("30th November 2026")
    editions[d2] = classified_page("15th December 2026")
    Ingestor(repo, FakeSource(editions)).run(days=[d1, d2])
    acct = next(j for j in jobs(repo) if j["title"] == "Accountant")
    assert acct["has_pending_revision"] is True
    assert acct["deadline"] == "2026-11-30"          # canonical value unchanged until a reviewer accepts
    rev = [r for r in repo.all("job_revisions") if r["job_id"] == acct["$id"]]
    assert len(rev) == 1 and rev[0]["changed_fields"] == ["deadline"] and rev[0]["status"] == "pending"


def test_missing_source_logs_failure_and_publishes_nothing(setup):
    repo, editions = setup
    result = Ingestor(repo, FakeSource(editions, fail=True)).run(days=[date(2026, 10, 23)])
    assert result["status"] == "FAILED" and "connection refused" in result["error"]
    assert jobs(repo) == []
    assert repo.all("ingestion_runs")[0]["status"] == "FAILED"


def test_no_edition_yet(setup):
    repo, editions = setup
    assert Ingestor(repo, FakeSource(editions)).run(days=[date(2026, 10, 23)])["status"] == "NO_NEW_EDITION"


def test_new_jobs_are_not_public_until_reviewed(setup):
    repo, editions = setup
    editions[date(2026, 10, 23)] = classified_page()
    Ingestor(repo, FakeSource(editions)).run(days=[date(2026, 10, 23)])
    assert all(j["review_status"] == "needs_review" and not j["$public"] for j in jobs(repo))


# ---------------------------------------------------------------- edition discovery

EDITION_HTML = """
<a class="current pagethumb thumbnail" data-ed_date="2026-10-23" data-alias="oheraldo" data-page="1"
   href="/epaper/oheraldo/2026-10-23/page/1"><img src="/uploads/epaper/2026-10/thumbnail-150-6adaa8a994b3b.jpg"></a>
<a class="pagethumb thumbnail" data-ed_date="2026-10-23" data-alias="oheraldo" data-page="2" data-id="1114"
   href="/epaper/oheraldo/1114/page/2"><img src="/uploads/epaper/2026-10/thumbnail-150-6adaa8af01e31.jpg"></a>
"""


def test_edition_discovery_parses_pages():
    ed = parse_edition_html(EDITION_HTML, date(2026, 10, 23), "u", "https://epaper.heraldgoa.in", "oheraldo")
    assert ed.edition_key == "oheraldo-2026-10-23" and ed.source_edition_id == "1114"
    assert [p.page_number for p in ed.pages] == [1, 2]
    assert ed.pages[0].image_url == "https://epaper.heraldgoa.in/uploads/epaper/2026-10/6adaa8a994b3b.jpg"


def test_edition_discovery_rejects_other_dates():
    assert parse_edition_html(EDITION_HTML, date(2026, 10, 22), "u", "b", "oheraldo") is None


# ---------------------------------------------------------------- matching regressions found on real pages (22/23 Oct 2026)

from paper2career.matching import filled_fields, find_match  # noqa: E402
from paper2career.models import JobDraft  # noqa: E402


def _job(title, text, phones=(), **fields):
    return {"$id": "job_x", "title": title, "description": text, "contact_phones": list(phones), **fields}


def test_subset_text_does_not_link_different_ads():
    old = _job("Waiter", "Wanted Waiter. 9822000000")
    merged = "Wanted Waiter. 9822000000 Liquor store in Margao seeks counter salesperson. Call 9112088990"
    draft = JobDraft(title="Waiter", contact_phones=["9822000000", "9112088990"])
    assert find_match(draft, merged, None, [old]).kind != "repeat"


def test_same_wording_different_advertiser_is_a_new_job():
    old = _job("Nanny", "Looking for a house help cum nanny at Raia. Interested candidate please contact 7972403405.",
               ["7972403405"])
    draft = JobDraft(title="Nanny", contact_phones=["9021248523"])
    text = "Looking for a house help cum nanny at Sao Jose de Areal. Interested candidate please contact 9021248523."
    assert find_match(draft, text, None, [old]).kind == "new"


def test_same_advertiser_changed_salary_is_flagged():
    old = _job("Accountant", "Wanted accountant with 2-3 years tally experience in Panjim. Salary 25000. 8806448765",
               ["8806448765"], salary_text="Salary 25000")
    draft = JobDraft(title="Accountant", contact_phones=["8806448765"], salary_text="Salary 20000")
    m = find_match(draft, "Wanted Accountant with 1 or 2 years experience. Salary 20000. 8806448765", None, [old])
    assert m.kind == "probable" and set(m.changes) == {"salary_text"} and m.needs_review


def test_newly_readable_field_fills_gap_without_review():
    text = "Need Factory worker to work on multiple roles. Location Cuncolim IDC. Contact 9763820500"
    old = _job("Factory Worker", text.replace("Cuncolim", "Cunco\im"), ["9763820500"], location=None)
    draft = JobDraft(title="Factory Worker", contact_phones=["9763820500"], location="Cuncolim")
    m = find_match(draft, text, None, [old])
    assert m.kind == "repeat" and not m.changes and filled_fields(old, draft) == {"location": "Cuncolim"}


def test_suffixed_booking_number_ends_an_ad():
    page = column(0, [["SITUATIONS VACANT"], ["Wanted Waiter for bar in Margao. 9822000000", "2026030842-1",
                                              "Wanted Cook for hotel in Panjim. 9822111111", "2026030843"]])
    page += column(400, [["Wanted Driver for Vasco firm. 9822222222", "2026030844", "Wanted Cleaner Calangute 9822333333",
                          "2026030845"]])
    refs = [a.ad_reference for a in extract.segment_ads(page)]
    assert refs == ["2026030842", "2026030843", "2026030844", "2026030845"]


def test_auto_publish_publishes_jobs_and_appearances_immediately(setup):
    repo, editions = setup
    d = date(2026, 10, 23)
    editions[d] = classified_page()
    Ingestor(repo, FakeSource(editions), auto_publish=True).run(days=[d])
    all_jobs = jobs(repo)
    assert len(all_jobs) == 4
    assert all(j["review_status"] == "published" and j["$public"] for j in all_jobs)
    all_apps = repo.all("job_appearances")
    assert len(all_apps) == 4
    assert all(a["$public"] for a in all_apps)


def test_contact_addressee_manager_is_not_extracted_as_job():
    ad = extract.Advertisement(
        text="Applications are invited for the posts of one Trained Undergraduate Teacher with B.A. B.Ed. and one Laboratory Assistant with XII Science on regular basis. Apply in writing with all testimonials, residence certificate and employment card to Manager M.E.F's Ayesha Girls' High School, Curti, Ponda, Goa, within 7 days.",
        lines=[], section="SITUATIONS VACANT", column=0, bbox=(0, 0, 100, 100), ocr_confidence=0.95, ad_reference="2026207801", terminated=True,
    )
    drafts = extract.extract_jobs(ad, date(2026, 10, 23))
    titles = [d.title for d in drafts]
    assert "Manager" not in titles
    assert "Undergraduate Teacher" in titles
    assert "Laboratory Assistant" in titles
    assert all(d.employer == "M.E.F's Ayesha Girls' High School" for d in drafts)


def test_salary_before_keyword_and_phone_not_captured():
    text = "Wanted fresher/ experience girl at aquem margao for back up office minimum 15000/- salary 7972921776/ 9699785186"
    ad = extract.Advertisement(
        text=text, lines=[], section="SITUATIONS VACANT", column=0, bbox=(0, 0, 100, 100),
        ocr_confidence=0.95, ad_reference="2026030720", terminated=True,
    )
    drafts = extract.extract_jobs(ad, date(2026, 10, 23))
    assert len(drafts) == 1
    assert drafts[0].salary_text == "minimum 15000/- salary"
    assert "7972921776" not in drafts[0].salary_text


def test_horizontal_strip_artifacts_rejected():
    # A thin wide horizontal strip across columns should be rejected by segment_ads
    lines = [
        OcrLine("Wanted Cook and Waiter for restaurant at Panjim. Call 9822112233.", 0, 100, 700, 135, 0.95),
        OcrLine("2026028524", 600, 136, 700, 150, 0.95),
    ]
    ads = extract.segment_ads(lines)
    # The bounding box width is 700, height is 50 (< 70) -> must be rejected
    assert len(ads) == 0


def test_wide_bounding_box_clamped_to_column():
    lines = [
        OcrLine("Wanted Cook for restaurant at Panjim. Call 9822112233.", 100, 100, 450, 130, 0.95),
        OcrLine("Experience 2 years required.", 100, 135, 450, 165, 0.95),
        OcrLine("2026028524", 300, 170, 450, 195, 0.95),
    ]
    ad = extract._make_ad(lines, "SITUATIONS VACANT")
    w = ad.bbox[2] - ad.bbox[0]
    assert w <= 600

