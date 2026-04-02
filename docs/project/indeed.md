# Indeed Scraper

**File**: `jobspy/indeed/__init__.py`
**Class**: `Indeed(Scraper)`
**Site enum**: `Site.INDEED`
**Job ID prefix**: `"in-{job_key}"`

---

## Overview

Indeed is scraped via a **private GraphQL API** (`apis.indeed.com/graphql`). The API requires a hardcoded API key and returns rich structured JSON including full job descriptions, company data, and compensation. No HTML parsing needed for the main data.

---

## HTTP Configuration

| Property | Value |
|---|---|
| API URL | `https://apis.indeed.com/graphql` |
| Base URL | `https://{domain}.indeed.com` (domain from `Country.indeed_domain_value`) |
| Session type | `RequestsRotating` (`is_tls=False`) |
| Retry | No |
| Headers | `jobspy/indeed/constant.py` → `api_headers` |
| SSL verify | `False` (hardcoded in the POST call) |

**Key headers** (from `api_headers`):

| Header | Value |
|---|---|
| `indeed-api-key` | `"161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8"` |
| `indeed-co` | Set at runtime to `Country.indeed_domain_value` (e.g., `"US"`) |
| `indeed-locale` | `"en-US"` |
| `User-Agent` | Simulates Indeed iPhone app |

---

## Country / Domain Selection

`Country.indeed_domain_value` returns `(subdomain, api_country_code)`:
- `Country.USA` → `("www", "US")`
- `Country.UK` → `("uk", "GB")`
- `Country.CANADA` → `("ca", "CA")`

Base URL becomes `https://{subdomain}.indeed.com`.
The `indeed-co` header is set to `api_country_code`.

---

## Search Request (GraphQL)

**Endpoint**: `POST https://apis.indeed.com/graphql`

**Payload**: `{"query": "<graphql_query_string>"}` (JSON body, not `variables` object)

The full query template is in `jobspy/indeed/constant.py` → `job_search_query`. It is a string with format placeholders:

| Placeholder | Value |
|---|---|
| `{what}` | `what: "{search_term}"` or empty string |
| `{location}` | `location: {where: "{location}", radius: {distance}, radiusUnit: MILES}` or empty |
| `{dateOnIndeed}` | `scraper_input.hours_old` integer value |
| `{cursor}` | `cursor: "{cursor_value}"` or empty |
| `{filters}` | Filter block string (see below) |

---

## Filter Building (`_build_filters()`)

**Important constraint**: `hours_old` filter **cannot** be combined with job_type/remote/easy_apply filters. Only one filter block is active at a time, in this priority:

### Priority 1: `hours_old` set
```graphql
filters: {
  date: {
    field: "dateOnIndeed",
    start: "{hours_old}h"
  }
}
```

### Priority 2: `easy_apply` set
```graphql
filters: {
  keyword: {
    field: "indeedApplyScope",
    keys: ["DESKTOP"]
  }
}
```

### Priority 3: `job_type` and/or `is_remote` set
```graphql
filters: {
  composite: {
    filters: [{
      keyword: {
        field: "attributes",
        keys: ["{keys}"]
      }
    }]
  }
}
```

Job type key mapping:

| `JobType` | Key |
|---|---|
| `FULL_TIME` | `"CF3CP"` |
| `PART_TIME` | `"75GKK"` |
| `CONTRACT` | `"NJXCK"` |
| `INTERNSHIP` | `"VDTG7"` |
| Remote | `"DSQF7"` |

Multiple keys are combined in the same `keys` array (e.g., FULL_TIME + remote → `["CF3CP", "DSQF7"]`).

---

## Pagination

- **Cursor-based** — `pageInfo.nextCursor` from each response feeds the next request
- **100 jobs per page** (`jobs_per_page = 100`)
- Continues until `seen_urls` count reaches `results_wanted + offset`
- Applies offset slicing at the end: `job_list[offset : offset + results_wanted]`

---

## Response Structure

```
data.jobSearch.results[]  → array of job wrappers
  .job                    → the actual job object
data.jobSearch.pageInfo.nextCursor  → next cursor string
```

---

## Job Field Extraction (`_process_job(job)`)

### Job URL & ID
- `job_url = "{base_url}/viewjob?jk={job['key']}"`
- `id = "in-{job['key']}"`
- Deduplication via `seen_urls` set

### Title
- `job["title"]`

### Description
- `job["description"]["html"]` — raw HTML
- Converted per `description_format`: MARKDOWN → `markdown_converter()`, otherwise returned as-is

### Job Type (`job_type`)
`jobspy/indeed/util.py` → `get_job_type(attributes)`:
- Iterates `job["attributes"]` list
- For each attribute: `label.replace("-", "").replace(" ", "").lower()` → `get_enum_from_job_type()`
- Returns `list[JobType]` (may have multiple matches)

### Remote Status (`is_remote`)
`jobspy/indeed/util.py` → `is_job_remote(job, description)`:
- Checks all three sources independently, returns True if any match:
  1. **Attributes**: any `attr["label"].lower()` contains `"remote"`, `"work from home"`, or `"wfh"`
  2. **Description**: description text contains those keywords
  3. **Location**: `job["location"]["formatted"]["long"]` contains those keywords

### Compensation (`compensation`)
`jobspy/indeed/util.py` → `get_compensation(job["compensation"])`:
- Prefers `compensation["baseSalary"]` over `compensation["estimated"]["baseSalary"]`
- `unitOfWork` → `CompensationInterval` mapping:
  | API value | Interval |
  |---|---|
  | `"DAY"` | `DAILY` |
  | `"YEAR"` | `YEARLY` |
  | `"HOUR"` | `HOURLY` |
  | `"WEEK"` | `WEEKLY` |
  | `"MONTH"` | `MONTHLY` |
- `min_amount` from `range.min`, `max_amount` from `range.max`
- Currency from `estimated.currencyCode` if estimated, else `currencyCode`

### Date Posted
- `job["datePublished"]` is millisecond timestamp
- `datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")`

### Location
- `job["location"]["city"]` → `city`
- `job["location"]["admin1Code"]` → `state` (US state code, e.g., `"CA"`)
- `job["location"]["countryCode"]` → `country` (raw string, not Country enum)

### Company Data
From `job["employer"]["dossier"]` (may be `None`):
- `company_name`: `job["employer"]["name"]`
- `company_url`: `"{base_url}{job['employer']['relativeCompanyPageUrl']}"`
- `company_url_direct`: `dossier["links"]["corporateWebsite"]`
- `company_logo`: `dossier["images"]["squareLogoUrl"]`
- `company_addresses`: `dossier["employerDetails"]["addresses"][0]` (first address)
- `company_industry`: `dossier["employerDetails"]["industry"]` cleaned:
  ```python
  .replace("Iv1", "").replace("_", " ").title().strip()
  ```
- `company_num_employees`: `dossier["employerDetails"]["employeesLocalizedLabel"]`
- `company_revenue`: `dossier["employerDetails"]["revenueLocalizedLabel"]`
- `company_description`: `dossier["employerDetails"]["briefDescription"]`

### Direct Job URL
- `job["recruit"]["viewJobUrl"]` — the employer's direct application page (may be None)

### Emails
- `extract_emails_from_text(description)` — regex on description text

---

## Fields Summary

| Field | Source |
|---|---|
| `title` | `job.title` |
| `description` | `job.description.html` (HTML → converted) |
| `job_type` | `job.attributes[].label` matched to `JobType` enum |
| `is_remote` | attributes + description + location text |
| `compensation` | `job.compensation.baseSalary` or `.estimated.baseSalary` |
| `date_posted` | `job.datePublished` (ms timestamp) |
| `location` | `job.location.city/admin1Code/countryCode` |
| `job_url` | constructed from `job.key` |
| `job_url_direct` | `job.recruit.viewJobUrl` |
| `company_*` fields | `job.employer.dossier` |

---

## Error Handling

- Non-200 response → logs status code, returns partial results
- Null `employer` / `dossier` objects handled with `.get()` / conditional checks
- Exception class: `IndeedException` (defined in `exception.py`, not explicitly raised in current code)

---

## Notes for AI Agents

- The `hours_old` filter is **mutually exclusive** with `job_type`/`is_remote`/`easy_apply` filters — this is an Indeed API constraint, not a bug
- `country_indeed` parameter in `scrape_jobs()` maps to `ScraperInput.country` and changes both the domain and the API country header
- Salary is preferred from `baseSalary` (employer-provided) over `estimated.baseSalary` (Indeed estimate)
- The GraphQL `what`/`location` fields are empty strings (not omitted) when not provided — the query template handles this
- `job["location"]["admin1Code"]` returns state abbreviation for US (e.g., `"CA"`) — not full state name
- 100 jobs per page makes this the most efficient scraper for large result sets
