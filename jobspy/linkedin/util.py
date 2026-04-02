from bs4 import BeautifulSoup

from jobspy.model import JobType, Location, WorkFormat, SeniorityLevel
from jobspy.util import get_enum_from_job_type

# Maps WorkFormat enum to LinkedIn f_WT query parameter values
LINKEDIN_WORK_FORMAT_CODE: dict[WorkFormat, int] = {
    WorkFormat.ONSITE: 1,
    WorkFormat.HYBRID: 3,
    WorkFormat.REMOTE: 2,
}

# Maps SeniorityLevel enum to LinkedIn f_E query parameter values.
#
# LinkedIn level → typical industry equivalents:
#   INTERNSHIP (1) — intern, trainee; no professional experience required
#   ENTRY      (2) — junior, 0–2 years exp; first full-time role
#   ASSOCIATE  (3) — junior-to-middle transition, 2–4 years exp; some companies skip this level
#   MID_SENIOR (4) — middle / senior, 4–8 years exp; the broadest LinkedIn bucket,
#                    covers both "Middle Software Engineer" and "Senior Software Engineer"
#   DIRECTOR   (5) — director, head-of, principal, staff; people or technical leadership
#   EXECUTIVE  (6) — C-level, VP, SVP; company-wide scope
LINKEDIN_SENIORITY_CODE: dict[SeniorityLevel, int] = {
    SeniorityLevel.INTERNSHIP: 1,
    SeniorityLevel.ENTRY: 2,
    SeniorityLevel.ASSOCIATE: 3,
    SeniorityLevel.MID_SENIOR: 4,
    SeniorityLevel.DIRECTOR: 5,
    SeniorityLevel.EXECUTIVE: 6,
}

# Maps raw text from LinkedIn detail page "Work type" block to WorkFormat enum
LINKEDIN_WORK_FORMAT_FROM_TEXT: dict[str, WorkFormat] = {
    "remote": WorkFormat.REMOTE,
    "hybrid": WorkFormat.HYBRID,
    "on-site": WorkFormat.ONSITE,
    "onsite": WorkFormat.ONSITE,
    "in person": WorkFormat.ONSITE,
}


def job_type_code(job_type_enum: JobType) -> str:
    return {
        JobType.FULL_TIME: "F",
        JobType.PART_TIME: "P",
        JobType.INTERNSHIP: "I",
        JobType.CONTRACT: "C",
        JobType.TEMPORARY: "T",
    }.get(job_type_enum, "")


def parse_job_type(soup_job_type: BeautifulSoup) -> list[JobType] | None:
    """
    Gets the job type from job page
    :param soup_job_type:
    :return: JobType
    """
    h3_tag = soup_job_type.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: "Employment type" in text,
    )
    employment_type = None
    if h3_tag:
        employment_type_span = h3_tag.find_next_sibling(
            "span",
            class_="description__job-criteria-text description__job-criteria-text--criteria",
        )
        if employment_type_span:
            employment_type = employment_type_span.get_text(strip=True)
            employment_type = employment_type.lower()
            employment_type = employment_type.replace("-", "")

    return [get_enum_from_job_type(employment_type)] if employment_type else []


def parse_job_level(soup_job_level: BeautifulSoup) -> str | None:
    """
    Gets the job level from job page
    :param soup_job_level:
    :return: str
    """
    h3_tag = soup_job_level.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: "Seniority level" in text,
    )
    job_level = None
    if h3_tag:
        job_level_span = h3_tag.find_next_sibling(
            "span",
            class_="description__job-criteria-text description__job-criteria-text--criteria",
        )
        if job_level_span:
            job_level = job_level_span.get_text(strip=True)

    return job_level


def parse_company_industry(soup_industry: BeautifulSoup) -> str | None:
    """
    Gets the company industry from job page
    :param soup_industry:
    :return: str
    """
    h3_tag = soup_industry.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: "Industries" in text,
    )
    industry = None
    if h3_tag:
        industry_span = h3_tag.find_next_sibling(
            "span",
            class_="description__job-criteria-text description__job-criteria-text--criteria",
        )
        if industry_span:
            industry = industry_span.get_text(strip=True)

    return industry


def parse_work_format_from_page(soup: BeautifulSoup) -> WorkFormat | None:
    """
    Tries to extract work format from LinkedIn job detail page criteria block.
    Returns None if 'Work type' block is absent — not all jobs include it.
    """
    h3_tag = soup.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: text and "Work type" in text.strip(),
    )
    if not h3_tag:
        return None
    span = h3_tag.find_next_sibling(
        "span",
        class_="description__job-criteria-text description__job-criteria-text--criteria",
    )
    if not span:
        return None
    return LINKEDIN_WORK_FORMAT_FROM_TEXT.get(span.get_text(strip=True).lower())


def determine_work_format(
    filter_work_format: WorkFormat | None,
    page_work_format: WorkFormat | None,
    title: str,
    description: str | None,
    location: Location,
    use_keyword_fallback: bool = True,
) -> WorkFormat | None:
    """
    Determines work format for a single job using a priority chain:
    1. Search filter value — LinkedIn guarantees all results match, most reliable
    2. Parsed from detail page — structural but not present on all jobs
    3. Keyword detection — fallback, least accurate, toggled by use_keyword_fallback
    """
    if filter_work_format is not None:
        return filter_work_format

    if page_work_format is not None:
        return page_work_format

    if use_keyword_fallback:
        location_str = location.display_location() if location else ""
        full_string = f'{title} {description or ""} {location_str}'.lower()
        if any(kw in full_string for kw in ("remote", "work from home", "wfh")):
            return WorkFormat.REMOTE
        if "hybrid" in full_string:
            return WorkFormat.HYBRID

    return None


def is_job_remote(work_format: WorkFormat | None) -> bool:
    """Derives is_remote bool from work_format."""
    return work_format == WorkFormat.REMOTE
