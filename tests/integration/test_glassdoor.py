"""
Integration tests for Glassdoor scraper.

Run:
    pytest tests/integration/test_glassdoor.py -v -m integration

Notes:
- 25-second delays between tests prevent Cloudflare IP-level blocking.
  First test can trigger ~23 requests (jobs page + per-job descriptions),
  which exhausts Glassdoor's short rate-limit window.
- curl_cffi is used for browser-grade TLS fingerprinting (see jobspy/util.py).
  Without it, Cloudflare managed-challenge returns 403 even on fresh sessions.
- PROXY env var is optional: set it to a residential US proxy for best results.
"""

import os
import time

import pytest
from dotenv import load_dotenv

from jobspy import scrape_jobs

load_dotenv()

proxy = os.getenv("PROXY")

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def throttle_glassdoor():
    """Pause after each test to stay within Glassdoor/Cloudflare rate limits.

    The first test in a suite can make ~23 requests (1 jobs page + 20 description
    fetches + CSRF + location). After that Cloudflare blocks the IP for ~20 seconds.
    """
    yield
    time.sleep(25)


EXPECTED_COLUMNS = {"title", "company", "job_url", "location", "date_posted", "description"}


def test_glassdoor_basic_scrape():
    """Core fields populated; work_format/seniority/hours_old params do not crash."""
    search = (
        "software engineer"
    )
    df = scrape_jobs(
        site_name="glassdoor",
        search_term=search,
        location="United States",
        work_format="remote",
        seniority_levels=["mid_senior"],
        results_wanted=100,
        hours_old=24,
        # proxies=proxy,
    )
    if df.empty:
        pytest.skip("Glassdoor returned no results — possible rate limit or geoblocking")

    assert EXPECTED_COLUMNS.issubset(df.columns), f"Missing columns: {EXPECTED_COLUMNS - set(df.columns)}"
    assert df["title"].notna().any(), "No job titles found"
    assert df["job_url"].str.contains("glassdoor.com").all(), "Unexpected job URLs"
    wf_dist = df["work_format"].value_counts().to_dict() if "work_format" in df.columns else {}
    print(f"\n[basic] results={len(df)}, work_formats={wf_dist}")


def test_glassdoor_remote_filter():
    """work_format=remote: all returned jobs with a known work_format should be remote."""
    df = scrape_jobs(
        site_name="glassdoor",
        search_term="software engineer",
        location="New York",
        work_format="onsite",
        results_wanted=50,
        # proxies=proxy,
        hours_old=24,
    )
    if df.empty:
        pytest.skip("Glassdoor returned no results")

    assert "work_format" in df.columns, "work_format column missing from output"
    wf_counts = df["work_format"].value_counts().to_dict()
    print(f"\n[remote] work_format distribution: {wf_counts}")

    non_remote = df[df["work_format"].notna() & (df["work_format"] != "remote")]
    assert len(non_remote) == 0, (
        f"Expected all remote, got: {non_remote[['title', 'work_format']].to_dict('records')}"
    )


def test_glassdoor_seniority_entry_level():
    """seniority_levels=['entry'] should return entry-level jobs."""
    df = scrape_jobs(
        site_name="glassdoor",
        search_term="software engineer",
        location="San Francisco",
        seniority_levels=["entry"],
        results_wanted=10,
        proxies=proxy,
    )
    if df.empty:
        pytest.skip("Glassdoor returned no results")

    assert df["title"].notna().any()
    print(f"\n[entry] titles: {df['title'].tolist()}")


def test_glassdoor_remote_and_seniority_combined():
    """Combining work_format=remote + seniority_levels=['mid_senior'] must not crash."""
    df = scrape_jobs(
        site_name="glassdoor",
        search_term="backend engineer",
        location="USA",
        work_format="remote",
        seniority_levels=["mid_senior"],
        results_wanted=10,
        proxies=proxy,
    )
    if df.empty:
        pytest.skip("Glassdoor returned no results")

    assert df["title"].notna().any()
    wf_dist = df["work_format"].value_counts().to_dict() if "work_format" in df.columns else "column missing"
    print(f"\n[remote+mid_senior] work_format={wf_dist}, titles={df['title'].tolist()[:5]}")


def test_glassdoor_no_location_fallback():
    """No location falls back to worldwide (id=11047) without crashing."""
    df = scrape_jobs(
        site_name="glassdoor",
        search_term="data analyst",
        location=None,
        results_wanted=10,
        proxies=proxy,
    )
    if df.empty:
        pytest.skip("Glassdoor returned no results")

    assert df["title"].notna().any()
    assert df["job_url"].str.contains("glassdoor.com").all()
    print(f"\n[no location] results={len(df)}")
