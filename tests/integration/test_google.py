"""
Integration tests for Google Jobs scraper.

Run:
    pytest tests/integration/test_google.py -v -m integration
"""

import pytest

from jobspy import scrape_jobs

pytestmark = pytest.mark.integration

SEARCH_TERM = "Python Developer"
LOCATION = "United States"
RESULTS = 3

EXPECTED_COLUMNS = {"title", "company", "job_url", "location", "date_posted", "description"}


def test_google_basic_scrape():
    """Google Jobs returns results and core fields are populated. New params must not crash it."""
    df = scrape_jobs(
        site_name="google",
        search_term=SEARCH_TERM,
        location=LOCATION,
        work_format="remote",
        seniority_levels=["mid_senior"],
        results_wanted=RESULTS,
        linkedin_use_keyword_work_format_fallback=False,
        linkedin_fetch_description=True,
        hours_old=24,
    )

    if df.empty:
        pytest.skip("Google Jobs returned no results — possible rate limit or geoblocking")
    assert EXPECTED_COLUMNS.issubset(df.columns), (
        f"Missing columns: {EXPECTED_COLUMNS - set(df.columns)}"
    )
    assert df["title"].notna().any(), "No job titles found"
