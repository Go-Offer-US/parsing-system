"""
Unit tests for hybrid work_format filtering in scrape_jobs().

Hybrid search is only supported by LinkedIn. When other sites are passed
alongside work_format="hybrid", they must be silently skipped (with a warning).
No real network calls are made — all scrapers are mocked.
"""

from unittest.mock import MagicMock, patch

from jobspy import scrape_jobs
from jobspy.model import JobResponse, ScraperInput, Site, SeniorityLevel, WorkFormat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_scraper(jobs: list | None = None):
    """Returns a mock scraper class whose .scrape() returns an empty JobResponse."""
    mock_cls = MagicMock()
    mock_cls.return_value.scrape.return_value = JobResponse(jobs=jobs or [])
    return mock_cls


def _patched_scrape(site_name, work_format, **kwargs):
    """Call scrape_jobs with all scrapers mocked out."""
    with (
        patch("jobspy.LinkedIn", _mock_scraper()) as li,
        patch("jobspy.Indeed", _mock_scraper()) as ind,
        patch("jobspy.Glassdoor", _mock_scraper()) as gd,
        patch("jobspy.ZipRecruiter", _mock_scraper()) as zr,
        patch("jobspy.Google", _mock_scraper()) as go,
    ):
        scrape_jobs(site_name=site_name, work_format=work_format, **kwargs)
        return li, ind, gd, zr, go


# ---------------------------------------------------------------------------
# Hybrid filtering — which scrapers are called
# ---------------------------------------------------------------------------

class TestHybridSiteFiltering:
    def test_only_linkedin_is_called_when_hybrid(self):
        """Indeed and Glassdoor must be skipped entirely for hybrid searches."""
        li, ind, gd, *_ = _patched_scrape(
            site_name=["linkedin", "indeed", "glassdoor"],
            work_format="hybrid",
        )
        li.return_value.scrape.assert_called_once()
        ind.return_value.scrape.assert_not_called()
        gd.return_value.scrape.assert_not_called()

    def test_linkedin_only_site_still_runs_for_hybrid(self):
        """If user already selected only LinkedIn, hybrid must proceed normally."""
        li, ind, *_ = _patched_scrape(
            site_name="linkedin",
            work_format="hybrid",
        )
        li.return_value.scrape.assert_called_once()
        ind.return_value.scrape.assert_not_called()

    def test_all_non_linkedin_sites_skipped_when_hybrid(self):
        """If only non-LinkedIn sites are passed with hybrid, nothing is scraped."""
        li, ind, gd, zr, go = _patched_scrape(
            site_name=["indeed", "glassdoor", "zip_recruiter", "google"],
            work_format="hybrid",
        )
        li.return_value.scrape.assert_not_called()
        ind.return_value.scrape.assert_not_called()
        gd.return_value.scrape.assert_not_called()
        zr.return_value.scrape.assert_not_called()
        go.return_value.scrape.assert_not_called()

    def test_remote_does_not_filter_any_site(self):
        """work_format=remote must not suppress any scraper."""
        li, ind, gd, *_ = _patched_scrape(
            site_name=["linkedin", "indeed", "glassdoor"],
            work_format="remote",
        )
        li.return_value.scrape.assert_called_once()
        ind.return_value.scrape.assert_called_once()
        gd.return_value.scrape.assert_called_once()

    def test_onsite_does_not_filter_any_site(self):
        """work_format=onsite must not suppress any scraper."""
        li, ind, gd, *_ = _patched_scrape(
            site_name=["linkedin", "indeed", "glassdoor"],
            work_format="onsite",
        )
        li.return_value.scrape.assert_called_once()
        ind.return_value.scrape.assert_called_once()
        gd.return_value.scrape.assert_called_once()

    def test_no_work_format_does_not_filter_any_site(self):
        """When work_format is not set, all scrapers must run."""
        li, ind, gd, *_ = _patched_scrape(
            site_name=["linkedin", "indeed", "glassdoor"],
            work_format=None,
        )
        li.return_value.scrape.assert_called_once()
        ind.return_value.scrape.assert_called_once()
        gd.return_value.scrape.assert_called_once()

    def test_hybrid_warning_is_logged(self):
        """A warning must be emitted when unsupported sites are silently skipped."""
        with patch("jobspy.log") as mock_log:
            _patched_scrape(
                site_name=["linkedin", "indeed"],
                work_format="hybrid",
            )
        mock_log.warning.assert_called_once()
        warning_msg = mock_log.warning.call_args[0][0]
        assert "hybrid" in warning_msg.lower()
        assert "indeed" in warning_msg.lower()


# ---------------------------------------------------------------------------
# ScraperInput construction
# ---------------------------------------------------------------------------

class TestScraperInputConstruction:
    def _make_input(self, **kwargs) -> ScraperInput:
        defaults = dict(
            site_type=[Site.LINKEDIN],
            search_term="engineer",
            location="New York",
            distance=25,
        )
        return ScraperInput(**{**defaults, **kwargs})

    def test_work_format_remote_stored_as_enum(self):
        si = self._make_input(work_format=WorkFormat.REMOTE)
        assert si.work_format == WorkFormat.REMOTE

    def test_work_format_hybrid_stored_as_enum(self):
        si = self._make_input(work_format=WorkFormat.HYBRID)
        assert si.work_format == WorkFormat.HYBRID

    def test_work_format_onsite_stored_as_enum(self):
        si = self._make_input(work_format=WorkFormat.ONSITE)
        assert si.work_format == WorkFormat.ONSITE

    def test_distance_default_is_none(self):
        si = self._make_input(distance=None)
        assert si.distance is None

    def test_seniority_levels_stored(self):
        si = self._make_input(seniority_levels=[SeniorityLevel.MID_SENIOR])
        assert si.seniority_levels == [SeniorityLevel.MID_SENIOR]


# ---------------------------------------------------------------------------
# ScraperInput.is_remote_search property
# ---------------------------------------------------------------------------

class TestIsRemoteSearch:
    def _si(self, **kwargs) -> ScraperInput:
        return ScraperInput(
            site_type=[Site.LINKEDIN],
            **kwargs,
        )

    def test_true_when_work_format_remote(self):
        assert self._si(work_format=WorkFormat.REMOTE).is_remote_search is True

    def test_true_when_is_remote_flag(self):
        assert self._si(is_remote=True).is_remote_search is True

    def test_false_when_work_format_hybrid(self):
        assert self._si(work_format=WorkFormat.HYBRID).is_remote_search is False

    def test_false_when_work_format_onsite(self):
        assert self._si(work_format=WorkFormat.ONSITE).is_remote_search is False

    def test_false_when_no_work_format(self):
        assert self._si().is_remote_search is False

    def test_is_remote_flag_ignored_when_work_format_set(self):
        # Explicit work_format=ONSITE must win over is_remote=True
        si = self._si(work_format=WorkFormat.ONSITE, is_remote=True)
        assert si.is_remote_search is False
