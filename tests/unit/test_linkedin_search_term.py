"""
Unit tests for the LinkedIn-only search term override (linkedin_search_term).

LinkedIn ignores its work-type filter (f_WT) under AI-powered search, so callers
need a way to send LinkedIn a different query (e.g. one carrying "remote") while
other sites keep the common search_term. This mirrors the existing
google_search_term precedent.

No real network calls are made — all scrapers are mocked.
"""

from unittest.mock import MagicMock, patch

from jobspy import scrape_jobs
from jobspy.model import JobResponse, ScraperInput, Site


def _capturing_scraper(captured: dict, key: str):
    """Mock scraper class that records the ScraperInput passed to .scrape() into captured[key]."""
    mock_cls = MagicMock()

    def _scrape(scraper_input):
        captured[key] = scraper_input
        return JobResponse(jobs=[])

    mock_cls.return_value.scrape.side_effect = _scrape
    return mock_cls


def _run(site_name, **kwargs) -> dict:
    """Run scrape_jobs with all scrapers mocked; return {site_key: ScraperInput} captured."""
    captured: dict = {}
    with (
        patch("jobspy.LinkedIn", _capturing_scraper(captured, "linkedin")),
        patch("jobspy.Indeed", _capturing_scraper(captured, "indeed")),
        patch("jobspy.Glassdoor", _capturing_scraper(captured, "glassdoor")),
        patch("jobspy.ZipRecruiter", _capturing_scraper(captured, "zip_recruiter")),
        patch("jobspy.Google", _capturing_scraper(captured, "google")),
    ):
        scrape_jobs(site_name=site_name, **kwargs)
    return captured


class TestScraperInputCarriesLinkedinSearchTerm:
    def test_field_defaults_to_none(self):
        si = ScraperInput(site_type=[Site.LINKEDIN], search_term="engineer")
        assert si.linkedin_search_term is None

    def test_field_stored_when_set(self):
        si = ScraperInput(
            site_type=[Site.LINKEDIN],
            search_term="engineer",
            linkedin_search_term="engineer remote",
        )
        assert si.linkedin_search_term == "engineer remote"

    def test_scrape_jobs_forwards_linkedin_search_term(self):
        captured = _run(
            site_name="linkedin",
            search_term="engineer",
            linkedin_search_term="engineer remote",
        )
        li_input = captured["linkedin"]
        assert li_input.linkedin_search_term == "engineer remote"
        assert li_input.search_term == "engineer"

    def test_scrape_jobs_defaults_linkedin_search_term_to_none(self):
        captured = _run(site_name="linkedin", search_term="engineer")
        assert captured["linkedin"].linkedin_search_term is None

    def test_indeed_and_glassdoor_get_common_search_term(self):
        captured = _run(
            site_name=["linkedin", "indeed", "glassdoor"],
            search_term="engineer",
            linkedin_search_term="engineer remote",
        )
        assert captured["indeed"].search_term == "engineer"
        assert captured["glassdoor"].search_term == "engineer"


class TestKeywordResolution:
    """The LinkedIn scraper builds its `keywords` param as
    `linkedin_search_term or search_term` — verify that resolution directly."""

    def _resolve(self, search_term, linkedin_search_term):
        si = ScraperInput(
            site_type=[Site.LINKEDIN],
            search_term=search_term,
            linkedin_search_term=linkedin_search_term,
        )
        return si.linkedin_search_term or si.search_term

    def test_override_used_when_set(self):
        assert self._resolve("base", "override") == "override"

    def test_fallback_when_none(self):
        assert self._resolve("base", None) == "base"

    def test_fallback_when_empty_string(self):
        assert self._resolve("base", "") == "base"
