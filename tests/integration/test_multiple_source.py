"""
Integration tests for multi-source scraping (LinkedIn + Indeed + Glassdoor).

Run:
    pytest tests/integration/test_multiple_source.py -v -m integration

Environment:
    PROXY — optional proxy URL (e.g. http://user:pass@host:port).
            If not set, requests go direct.

Notes:
    - linkedin_fetch_description=True fetches full job descriptions from LinkedIn.
    - Hybrid search is only supported by LinkedIn — Indeed and Glassdoor are skipped
      automatically with a warning (see TestHybridSiteFiltering unit tests).
"""

import os

import pandas as pd
import pytest
from fake_useragent import UserAgent

from jobspy import scrape_jobs

pytestmark = pytest.mark.integration

SITES = ["linkedin", "indeed", "glassdoor"]
SEARCH_TERM = "Software Engineer"
RESULTS = 10
EXPECTED_COLUMNS = {"title", "company", "job_url", "location", "site", "work_format"}

proxy = os.getenv("PROXY")


def fake_useragent() -> str:
    return UserAgent().random


def _scrape(work_format: str, location: str, **kwargs) -> pd.DataFrame:
    """Shared scrape_jobs call with prod-like parameters."""
    is_remote = work_format == "remote"
    return scrape_jobs(
        site_name=SITES,
        search_term=SEARCH_TERM,
        location=location,
        results_wanted=RESULTS,
        offset=0,
        is_remote=is_remote,
        work_format=work_format,
        seniority_levels=["mid_senior"],
        job_type=None,
        linkedin_fetch_description=True,
        linkedin_company_ids=None,
        hours_old=24,
        proxies=proxy,
        user_agent=fake_useragent(),
        verbose=2,
        **kwargs,
    )


def _assert_basic(df: pd.DataFrame, work_format: str) -> None:
    assert not df.empty, f"No results returned for work_format={work_format!r}"
    assert EXPECTED_COLUMNS.issubset(df.columns), (
        f"Missing columns: {EXPECTED_COLUMNS - set(df.columns)}"
    )
    assert df["title"].notna().any(), "No job titles found"
    assert df["job_url"].notna().any(), "No job URLs found"


def test_multi_source_remote():
    """All three sites return remote jobs; LinkedIn results include full descriptions."""
    df = _scrape(work_format="remote", location="United States")

    _assert_basic(df, "remote")

    sites_present = set(df["site"].unique())
    assert sites_present, "No sites returned data"

    # LinkedIn results must have descriptions (fetch_description=True)
    linkedin_df = df[df["site"] == "linkedin"]
    if not linkedin_df.empty:
        assert linkedin_df["description"].notna().any(), (
            "LinkedIn descriptions are empty despite linkedin_fetch_description=True"
        )

    # Remote jobs should not have onsite work_format
    non_remote = df[df["work_format"].notna() & (df["work_format"] == "onsite")]
    assert len(non_remote) == 0, (
        f"Found {len(non_remote)} onsite jobs in remote search"
    )


def test_multi_source_onsite():
    """All three sites return onsite jobs with a location and distance filter."""
    df = _scrape(work_format="onsite", location="New York, NY", distance=25)

    _assert_basic(df, "onsite")

    sites_present = set(df["site"].unique())
    assert sites_present, "No sites returned data"

    # Onsite jobs must not be marked as remote
    remote_jobs = df[df["is_remote"].eq(True)]
    assert len(remote_jobs) == 0, (
        f"Found {len(remote_jobs)} remote-flagged jobs in onsite search"
    )


def test_multi_source_hybrid():
    """
    Hybrid search: only LinkedIn runs (Indeed/Glassdoor are skipped automatically).
    Verifies that results come exclusively from LinkedIn.
    """
    df = _scrape(work_format="hybrid", location="United States")

    if df.empty:
        pytest.skip("LinkedIn returned no hybrid results — possible rate limit")

    assert EXPECTED_COLUMNS.issubset(df.columns), (
        f"Missing columns: {EXPECTED_COLUMNS - set(df.columns)}"
    )

    # Only LinkedIn should have data — other sites must be absent
    sites_present = set(df["site"].unique())
    assert sites_present == {"linkedin"}, (
        f"Expected only linkedin, got: {sites_present}"
    )
