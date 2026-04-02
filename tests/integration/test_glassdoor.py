"""
Integration tests for Glassdoor scraper.

Run:
    pytest tests/integration/test_glassdoor.py -v -m integration
"""

import pytest

from jobspy import scrape_jobs

pytestmark = pytest.mark.integration

SEARCH_TERM = "Python Developer"
LOCATION = "United States"
RESULTS = 3

EXPECTED_COLUMNS = {"title", "company", "job_url", "location", "date_posted", "description"}


def test_glassdoor_basic_scrape():
    """Glassdoor returns results and core fields are populated. New params must not crash it."""
    df = scrape_jobs(
        site_name="glassdoor",
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
        pytest.skip("Glassdoor returned no results — possible rate limit, CSRF issue, or geoblocking")
    assert EXPECTED_COLUMNS.issubset(df.columns), (
        f"Missing columns: {EXPECTED_COLUMNS - set(df.columns)}"
    )
    assert df["title"].notna().any(), "No job titles found"
    assert df["job_url"].str.contains("glassdoor.com").all(), "Unexpected job URLs"
