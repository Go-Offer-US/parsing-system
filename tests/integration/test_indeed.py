"""
Integration tests for Indeed scraper.

Run:
    pytest tests/integration/test_indeed.py -v -m integration
"""

import pytest

from jobspy import scrape_jobs

from dotenv import load_dotenv
import os

load_dotenv()

proxy = os.getenv("PROXY")

pytestmark = pytest.mark.integration

SEARCH_TERM = "Technical project manager OR IT Manager OR IT business analyst OR IT Project manager OR IT Operations manager OR IT service analyst OR IT project coordinator OR IT project specialist OR PMO specialist OR PMO manager OR Project manager OR associate project manager OR Operations Project Manager OR Senior technical project manager"
LOCATION = "USA"
LOCATION_ONSITE = "New York, NY"
RESULTS = 100

EXPECTED_COLUMNS = {"title", "company", "job_url", "location", "date_posted", "description"}

def test_indeed_basic_scrape():
    """Indeed returns results and core fields are populated. New params must not crash it."""
    df = scrape_jobs(
        site_name="indeed",
        search_term=SEARCH_TERM,
        location=LOCATION,
        work_format="remote",
        is_remote=True,
        seniority_levels=["mid_senior"],
        results_wanted=RESULTS,
        linkedin_use_keyword_work_format_fallback=False,
        linkedin_fetch_description=True,
        hours_old=24,
        proxies=proxy,
        indeed_filter_priority="attributes",
    )

    assert not df.empty, "Indeed returned no results — possible rate limit or API change"
    assert EXPECTED_COLUMNS.issubset(df.columns), (
        f"Missing columns: {EXPECTED_COLUMNS - set(df.columns)}"
    )
    assert df["title"].notna().any(), "No job titles found"
    assert df["job_url"].str.contains("indeed.com").all(), "Unexpected job URLs"


def test_indeed_basic_scrape_onsite():
    """Indeed returns results and core fields are populated. New params must not crash it."""
    df = scrape_jobs(
        site_name="indeed",
        search_term=SEARCH_TERM,
        location=LOCATION_ONSITE,
        work_format="onsite",
        is_remote=False,
        seniority_levels=["mid_senior"],
        results_wanted=RESULTS,
        linkedin_use_keyword_work_format_fallback=False,
        linkedin_fetch_description=True,
        hours_old=24,
        proxies=proxy,
        indeed_filter_priority="date",
    )

    assert not df.empty, "Indeed returned no results — possible rate limit or API change"
    assert EXPECTED_COLUMNS.issubset(df.columns), (
        f"Missing columns: {EXPECTED_COLUMNS - set(df.columns)}"
    )
    assert df["title"].notna().any(), "No job titles found"
    assert df["job_url"].str.contains("indeed.com").all(), "Unexpected job URLs"