"""
Unit tests for Indeed._build_filters().

Verifies that the correct GraphQL filter string is generated for every
combination of scraper parameters — without making any network calls.
"""

from unittest.mock import patch

from jobspy.indeed import Indeed
from jobspy.model import JobType, ScraperInput, Site, WorkFormat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scraper(
    work_format: WorkFormat | None = None,
    is_remote: bool = False,
    hours_old: int | None = None,
    job_type: JobType | None = None,
    easy_apply: bool | None = None,
    indeed_filter_priority: str = "date",
) -> Indeed:
    """Build an Indeed instance with scraper_input set, session mocked out."""
    with patch("jobspy.indeed.create_session"):
        scraper = Indeed()

    scraper.scraper_input = ScraperInput(
        site_type=[Site.INDEED],
        work_format=work_format,
        is_remote=is_remote,
        hours_old=hours_old,
        job_type=job_type,
        easy_apply=easy_apply,
        indeed_filter_priority=indeed_filter_priority,
    )
    return scraper


def _filters(scraper: Indeed) -> str:
    """Return normalised filter string (collapsed whitespace) for easy assertions."""
    return " ".join(scraper._build_filters().split())


# ---------------------------------------------------------------------------
# No filters
# ---------------------------------------------------------------------------

class TestNoFilters:
    def test_empty_when_no_params(self):
        scraper = _make_scraper()
        assert _filters(scraper) == ""


# ---------------------------------------------------------------------------
# Date filter (hours_old)
# ---------------------------------------------------------------------------

class TestDateFilter:
    def test_date_filter_present(self):
        scraper = _make_scraper(hours_old=24)
        result = _filters(scraper)
        assert 'field: "dateOnIndeed"' in result
        assert 'start: "24h"' in result

    def test_date_filter_hours_value(self):
        scraper = _make_scraper(hours_old=72)
        assert 'start: "72h"' in _filters(scraper)

    def test_date_filter_no_composite(self):
        """hours_old alone must not produce composite block."""
        scraper = _make_scraper(hours_old=24)
        assert "composite" not in _filters(scraper)


# ---------------------------------------------------------------------------
# Composite filter (work_format / job_type)
# ---------------------------------------------------------------------------

class TestCompositeFilter:
    def test_remote_work_format_adds_dsqf7(self):
        scraper = _make_scraper(work_format=WorkFormat.REMOTE)
        result = _filters(scraper)
        assert "composite" in result
        assert "DSQF7" in result

    def test_is_remote_flag_adds_dsqf7(self):
        scraper = _make_scraper(is_remote=True)
        result = _filters(scraper)
        assert "DSQF7" in result

    def test_onsite_work_format_no_composite(self):
        scraper = _make_scraper(work_format=WorkFormat.ONSITE)
        assert _filters(scraper) == ""

    def test_hybrid_work_format_no_composite(self):
        scraper = _make_scraper(work_format=WorkFormat.HYBRID)
        assert _filters(scraper) == ""

    def test_full_time_job_type(self):
        scraper = _make_scraper(job_type=JobType.FULL_TIME)
        result = _filters(scraper)
        assert "composite" in result
        assert "CF3CP" in result

    def test_part_time_job_type(self):
        scraper = _make_scraper(job_type=JobType.PART_TIME)
        assert "75GKK" in _filters(scraper)

    def test_contract_job_type(self):
        scraper = _make_scraper(job_type=JobType.CONTRACT)
        assert "NJXCK" in _filters(scraper)

    def test_internship_job_type(self):
        scraper = _make_scraper(job_type=JobType.INTERNSHIP)
        assert "VDTG7" in _filters(scraper)

    def test_job_type_and_remote_both_in_keys(self):
        """Both job type key and DSQF7 must appear in the same composite block."""
        scraper = _make_scraper(job_type=JobType.FULL_TIME, work_format=WorkFormat.REMOTE)
        result = _filters(scraper)
        assert "CF3CP" in result
        assert "DSQF7" in result
        assert result.count("composite") == 1  # single block, not two


# ---------------------------------------------------------------------------
# Priority: date vs attributes (Indeed API only accepts one filter type)
# ---------------------------------------------------------------------------

class TestFilterPriority:
    def test_date_priority_keeps_date_drops_remote(self):
        """Default priority=date: hours_old wins, DSQF7 is dropped."""
        scraper = _make_scraper(
            hours_old=24, work_format=WorkFormat.REMOTE, indeed_filter_priority="date"
        )
        result = _filters(scraper)
        assert 'start: "24h"' in result
        assert "DSQF7" not in result
        assert "composite" not in result

    def test_date_priority_keeps_date_drops_job_type(self):
        scraper = _make_scraper(
            hours_old=48, job_type=JobType.FULL_TIME, indeed_filter_priority="date"
        )
        result = _filters(scraper)
        assert 'start: "48h"' in result
        assert "CF3CP" not in result

    def test_attributes_priority_keeps_remote_drops_date(self):
        """priority=attributes: DSQF7 wins, hours_old is dropped."""
        scraper = _make_scraper(
            hours_old=24, work_format=WorkFormat.REMOTE, indeed_filter_priority="attributes"
        )
        result = _filters(scraper)
        assert "DSQF7" in result
        assert "composite" in result
        assert "dateOnIndeed" not in result

    def test_attributes_priority_keeps_job_type_drops_date(self):
        scraper = _make_scraper(
            hours_old=24, job_type=JobType.CONTRACT, indeed_filter_priority="attributes"
        )
        result = _filters(scraper)
        assert "NJXCK" in result
        assert "dateOnIndeed" not in result

    def test_no_conflict_date_only(self):
        """No conflict when only hours_old is set — date filter applied as usual."""
        scraper = _make_scraper(hours_old=24)
        result = _filters(scraper)
        assert 'start: "24h"' in result

    def test_no_conflict_attributes_only(self):
        """No conflict when only work_format is set — composite applied as usual."""
        scraper = _make_scraper(work_format=WorkFormat.REMOTE)
        result = _filters(scraper)
        assert "DSQF7" in result
        assert "dateOnIndeed" not in result


# ---------------------------------------------------------------------------
# easy_apply (standalone — incompatible with composite)
# ---------------------------------------------------------------------------

class TestEasyApplyFilter:
    def test_easy_apply_uses_keyword_filter(self):
        scraper = _make_scraper(easy_apply=True)
        result = _filters(scraper)
        assert "indeedApplyScope" in result
        assert "DESKTOP" in result

    def test_easy_apply_takes_priority_over_others(self):
        """easy_apply must short-circuit and not add composite or date blocks."""
        scraper = _make_scraper(
            easy_apply=True, work_format=WorkFormat.REMOTE, hours_old=24
        )
        result = _filters(scraper)
        assert "indeedApplyScope" in result
        assert "DSQF7" not in result
        assert "dateOnIndeed" not in result
