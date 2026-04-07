"""
Integration tests for LinkedIn scraper.

These tests hit real LinkedIn — run them manually, not in CI.
    pytest tests/integration/test_linkedin.py -v -m integration
"""

import pytest
import pandas as pd

from jobspy import scrape_jobs

pytestmark = pytest.mark.integration

SEARCH_TERM = "Product Designer OR UX Designer OR User Experience Designer OR UI/UX Designer OR Senior UI/UX Designer OR Senior Experience Designer OR Senior Product Designer"
LOCATION = "United States"
RESULTS = 20  # Keep low to avoid rate limits


@pytest.fixture(scope="module")
def remote_jobs() -> pd.DataFrame:
    """Fetch remote jobs once per module — shared across tests that need it."""
    df = scrape_jobs(
        site_name="linkedin",
        search_term=SEARCH_TERM,
        location=LOCATION,
        work_format="remote",
        is_remote=True,
        seniority_levels=["mid_senior"],
        results_wanted=RESULTS,
        linkedin_use_keyword_work_format_fallback=False,
        linkedin_fetch_description=True,
        hours_old=24,
        verbose=2
    )
    assert not df.empty, "LinkedIn returned no results — possible rate limit (429)"
    return df


@pytest.fixture(scope="module")
def hybrid_jobs() -> pd.DataFrame:
    df = scrape_jobs(
        site_name="linkedin",
        search_term=SEARCH_TERM,
        location=LOCATION,
        work_format="hybrid",
        results_wanted=RESULTS,
        linkedin_use_keyword_work_format_fallback=False,
        linkedin_fetch_description=True,
        hours_old=24,
        verbose=2
    )
    assert not df.empty, "LinkedIn returned no results — possible rate limit (429)"
    return df


class TestWorkFormatFilter:
    def test_remote_filter_sets_work_format(self, remote_jobs):
        """All results must have work_format='remote' when filter is applied."""
        assert (remote_jobs["work_format"] == "remote").all(), (
            f"Expected all work_format='remote', got:\n{remote_jobs['work_format'].value_counts()}"
        )

    def test_remote_filter_syncs_is_remote(self, remote_jobs):
        """is_remote must be True for all remote results."""
        assert remote_jobs["is_remote"].all(), (
            "is_remote should be True for all jobs when work_format='remote'"
        )

    def test_hybrid_filter_sets_work_format(self, hybrid_jobs):
        """All results must have work_format='hybrid' when filter is applied."""
        assert (hybrid_jobs["work_format"] == "hybrid").all(), (
            f"Expected all work_format='hybrid', got:\n{hybrid_jobs['work_format'].value_counts()}"
        )

    def test_hybrid_filter_is_not_remote(self, hybrid_jobs):
        """Hybrid jobs must not be marked as remote."""
        assert not hybrid_jobs["is_remote"].any(), (
            "is_remote should be False for all hybrid jobs"
        )


class TestSeniorityFilter:
    def test_seniority_filter_returns_results(self):
        """Seniority filter should narrow results, not break the query."""
        df = scrape_jobs(
            site_name="linkedin",
            search_term=SEARCH_TERM,
            location=LOCATION,
            seniority_levels=["mid_senior", "entry"],
            results_wanted=RESULTS,
            verbose=2
        )
        assert not df.empty, "Seniority filter returned no results"
        assert "title" in df.columns


class TestBackwardCompatibility:
    def test_is_remote_true_still_works(self):
        """Legacy is_remote=True param must continue to return remote jobs."""
        df = scrape_jobs(
            site_name="linkedin",
            search_term=SEARCH_TERM,
            location=LOCATION,
            is_remote=True,
            results_wanted=RESULTS,
        )
        assert not df.empty, "is_remote=True returned no results"
        # work_format should be "remote" — filter inference applies
        assert (df["work_format"] == "remote").all(), (
            "is_remote=True should map to work_format='remote' via f_WT=3"
        )


class TestOnsiteNewYork:
    @pytest.fixture(scope="class")
    def onsite_ny_jobs(self) -> pd.DataFrame:
        df = scrape_jobs(
            site_name="linkedin",
            search_term=SEARCH_TERM,
            location="New York, NY",
            work_format="onsite",
            results_wanted=10,
            seniority_levels=["mid_senior"],
            linkedin_use_keyword_work_format_fallback=False,
            linkedin_fetch_description=True,
            hours_old=24,
            verbose=2
        )
        assert not df.empty, "LinkedIn returned no results — possible rate limit (429)"
        return df

    def test_onsite_filter_sets_work_format(self, onsite_ny_jobs):
        """All results must have work_format='onsite' when filter is applied."""
        assert (onsite_ny_jobs["work_format"] == "onsite").all(), (
            f"Expected all work_format='onsite', got:\n{onsite_ny_jobs['work_format'].value_counts()}"
        )

    def test_onsite_is_not_remote(self, onsite_ny_jobs):
        """Onsite jobs must not be marked as remote."""
        assert not onsite_ny_jobs["is_remote"].any(), (
            "is_remote should be False for all onsite jobs"
        )

    def test_onsite_location_contains_new_york(self, onsite_ny_jobs):
        """Results should be located in or around New York."""
        ny_keywords = ("new york", "ny", "brooklyn", "queens", "bronx", "manhattan", "newark", "hoboken")
        has_ny = onsite_ny_jobs["location"].str.lower().apply(
            lambda loc: any(kw in loc for kw in ny_keywords) if isinstance(loc, str) else False
        )
        assert has_ny.any(), (
            f"Expected at least some results near New York, got locations:\n{onsite_ny_jobs['location'].unique()}"
        )


class TestKeywordFallback:
    def test_fallback_disabled_without_filter(self):
        """With no filter and fallback disabled, work_format should be None for all jobs."""
        df = scrape_jobs(
            site_name="linkedin",
            search_term=SEARCH_TERM,
            location=LOCATION,
            results_wanted=RESULTS,
            linkedin_use_keyword_work_format_fallback=False,
        )
        assert not df.empty, "Search returned no results"
        # Without filter and without fallback, work_format must be None
        # (linkedin_fetch_description=False by default — no detail page parsing)
        assert df["work_format"].isna().all(), (
            "work_format should be None when no filter and fallback is disabled"
        )
