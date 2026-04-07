from __future__ import annotations

import math
from datetime import datetime
from typing import Tuple

from jobspy.indeed.constant import job_search_query, api_headers
from jobspy.indeed.util import is_job_remote, get_compensation, get_job_type
from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    Location,
    JobResponse,
    JobType,
    DescriptionFormat,
    WorkFormat,
)
from jobspy.util import (
    extract_emails_from_text,
    markdown_converter,
    create_session,
    create_logger,
)

log = create_logger("Indeed")


class Indeed(Scraper):
    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes IndeedScraper with the Indeed API url
        """
        super().__init__(Site.INDEED, proxies=proxies)

        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert, is_tls=False
        )
        self.scraper_input = None
        self.jobs_per_page = 100
        self.num_workers = 10
        self.seen_urls = set()
        self.headers = None
        self.api_country_code = None
        self.base_url = None
        self.api_url = "https://apis.indeed.com/graphql"

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes Indeed for jobs with scraper_input criteria
        :param scraper_input:
        :return: job_response
        """
        self.scraper_input = scraper_input
        domain, self.api_country_code = self.scraper_input.country.indeed_domain_value
        self.base_url = f"https://{domain}.indeed.com"
        self.headers = api_headers.copy()
        self.headers["indeed-co"] = self.scraper_input.country.indeed_domain_value
        job_list = []
        page = 1

        cursor = None

        while len(self.seen_urls) < scraper_input.results_wanted + scraper_input.offset:
            log.info(
                f"search page: {page} / {math.ceil(scraper_input.results_wanted / self.jobs_per_page)}"
            )
            jobs, cursor = self._scrape_page(cursor)
            if not jobs:
                log.info(f"found no jobs on page: {page}")
                break
            job_list += jobs
            page += 1
        return JobResponse(
            jobs=job_list[
                scraper_input.offset : scraper_input.offset
                + scraper_input.results_wanted
            ]
        )

    def _scrape_page(self, cursor: str | None) -> Tuple[list[JobPost], str | None]:
        """
        Scrapes a page of Indeed for jobs with scraper_input criteria
        :param cursor:
        :return: jobs found on page, next page cursor
        """
        jobs = []
        new_cursor = None
        filters = self._build_filters()
        search_term = (
            self.scraper_input.search_term.replace('"', '\\"')
            if self.scraper_input.search_term
            else ""
        )
        query = job_search_query.format(
            what=(f'what: "{search_term}"' if search_term else ""),
            location=(
                self._build_location_filter()
                if self.scraper_input.location
                else ""
            ),
            dateOnIndeed=self.scraper_input.hours_old,
            cursor=f'cursor: "{cursor}"' if cursor else "",
            filters=filters,
        )
        payload = {
            "query": query,
        }
        api_headers_temp = api_headers.copy()
        api_headers_temp["indeed-co"] = self.api_country_code
        response = self.session.post(
            self.api_url,
            headers=api_headers_temp,
            json=payload,
            timeout=10,
            verify=False,
        )
        if not response.ok:
            log.info(
                f"responded with status code: {response.status_code} (submit GitHub issue if this appears to be a bug). Reason: {response.text}"
            )
            return jobs, new_cursor
        data = response.json()
        jobs = data["data"]["jobSearch"]["results"]
        new_cursor = data["data"]["jobSearch"]["pageInfo"]["nextCursor"]

        job_list = []
        for job in jobs:
            processed_job = self._process_job(job["job"])
            if processed_job:
                job_list.append(processed_job)

        return job_list, new_cursor

    def _build_location_filter(self) -> str:
        location = self.scraper_input.location
        distance = self.scraper_input.distance or 50
        return f'location: {{where: "{location}", radius: {distance}, radiusUnit: MILES}}'

    def _build_filters(self) -> str:
        """
        Builds the GraphQL filters string.

        Indeed API accepts only one filter type per request (date, composite, or keyword).
        When both hours_old and work_format/job_type are set, indeed_filter_priority decides
        which one is applied. The dropped filter is logged as a warning.
        """
        si = self.scraper_input

        if si.easy_apply:
            return """
            filters: {
                keyword: {
                  field: "indeedApplyScope",
                  keys: ["DESKTOP"]
                }
            }
            """

        job_type_key_mapping = {
            JobType.FULL_TIME: "CF3CP",
            JobType.PART_TIME: "75GKK",
            JobType.CONTRACT: "NJXCK",
            JobType.INTERNSHIP: "VDTG7",
        }
        attribute_keys: list[str] = []
        if si.job_type and si.job_type in job_type_key_mapping:
            attribute_keys.append(job_type_key_mapping[si.job_type])
        if si.is_remote_search:
            attribute_keys.append("DSQF7")

        has_date = bool(si.hours_old)
        has_attributes = bool(attribute_keys)

        if has_date and has_attributes:
            if si.indeed_filter_priority == "attributes":
                log.warning(
                    f"Indeed: hours_old={si.hours_old} ignored — "
                    f"indeed_filter_priority='attributes' takes precedence"
                )
                has_date = False
            else:
                log.warning(
                    f"Indeed: work_format/job_type filter ignored — "
                    f"indeed_filter_priority='date' takes precedence (hours_old={si.hours_old})"
                )
                has_attributes = False

        if has_date:
            return f"""
            filters: {{
                date: {{
                  field: "dateOnIndeed",
                  start: "{si.hours_old}h"
                }}
            }}
            """

        if has_attributes:
            keys_str = '", "'.join(attribute_keys)
            return f"""
            filters: {{
              composite: {{
                filters: [{{
                  keyword: {{
                    field: "attributes",
                    keys: ["{keys_str}"]
                  }}
                }}]
              }}
            }}
            """

        return ""

    def _process_job(self, job: dict) -> JobPost | None:
        """
        Parses the job dict into JobPost model
        :param job: dict to parse
        :return: JobPost if it's a new job
        """
        job_url = f'{self.base_url}/viewjob?jk={job["key"]}'
        if job_url in self.seen_urls:
            return
        self.seen_urls.add(job_url)
        description = job["description"]["html"]
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            description = markdown_converter(description)

        job_type = get_job_type(job["attributes"])
        timestamp_seconds = job["datePublished"] / 1000
        date_posted = datetime.fromtimestamp(timestamp_seconds).strftime("%Y-%m-%d")
        employer = job["employer"].get("dossier") if job["employer"] else None
        employer_details = employer.get("employerDetails", {}) if employer else {}
        rel_url = job["employer"]["relativeCompanyPageUrl"] if job["employer"] else None
        return JobPost(
            id=f'in-{job["key"]}',
            title=job["title"],
            description=description,
            company_name=job["employer"].get("name") if job.get("employer") else None,
            company_url=(f"{self.base_url}{rel_url}" if job["employer"] else None),
            company_url_direct=(
                employer["links"]["corporateWebsite"] if employer else None
            ),
            location=Location(
                city=job.get("location", {}).get("city"),
                state=job.get("location", {}).get("admin1Code"),
                country=job.get("location", {}).get("countryCode"),
            ),
            job_type=job_type,
            compensation=get_compensation(job["compensation"]),
            date_posted=date_posted,
            job_url=job_url,
            job_url_direct=(
                job["recruit"].get("viewJobUrl") if job.get("recruit") else None
            ),
            emails=extract_emails_from_text(description) if description else None,
            is_remote=(remote := is_job_remote(job, description)),
            work_format=WorkFormat.REMOTE if remote else WorkFormat.ONSITE,
            company_addresses=(
                employer_details["addresses"][0]
                if employer_details.get("addresses")
                else None
            ),
            company_industry=(
                employer_details["industry"]
                .replace("Iv1", "")
                .replace("_", " ")
                .title()
                .strip()
                if employer_details.get("industry")
                else None
            ),
            company_num_employees=employer_details.get("employeesLocalizedLabel"),
            company_revenue=employer_details.get("revenueLocalizedLabel"),
            company_description=employer_details.get("briefDescription"),
            company_logo=(
                employer["images"].get("squareLogoUrl")
                if employer and employer.get("images")
                else None
            ),
        )
