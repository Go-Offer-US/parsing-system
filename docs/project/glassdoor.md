# Glassdoor Scraper

**File**: `jobspy/glassdoor/__init__.py`
**Class**: `Glassdoor(Scraper)`
**Site enum**: `Site.GLASSDOOR`
**Job ID prefix**: `"gd-{listing_id}"`

---

## Overview

Glassdoor is scraped via a **private GraphQL API** (`{base_url}/graph`). The scraper requires a CSRF token fetched from a generic Glassdoor page before any search. Job descriptions are fetched separately via a second GraphQL call per job. Location resolution also requires a preliminary AJAX call.

---

## HTTP Configuration

| Property | Value |
|---|---|
| Base URL | From `Country.get_glassdoor_url()` (e.g., `https://www.glassdoor.com/`) |
| API endpoint | `{base_url}/graph` (POST) |
| Session type | `RequestsRotating` (`is_tls=True` by default via `create_session`) |
| Retry | Yes (`has_retry=True`) |
| Max results | Capped at 900 (`self.scraper_input.results_wanted = min(900, ...)`) |
| Jobs per page | 30 (`numJobsToShow: 30`) |
| Max pages | 30 |
| Headers | `jobspy/glassdoor/constant.py` → `headers` dict |

**Key headers** (from `constant.py`):
- `gd-csrf-token`: set at runtime (fetched or fallback)
- Standard browser headers (User-Agent, Accept, etc.)

---

## Country / Domain Selection

`Country.glassdoor_domain_value` property returns the glassdoor hostname:
- `Country.USA` → `"www.glassdoor.com"` → base URL: `"https://www.glassdoor.com/"`
- `Country.UK` → `"www.glassdoor.co.uk"` → base URL: `"https://www.glassdoor.co.uk/"`
- `Country.GERMANY` → `"www.glassdoor.de"` → base URL: `"https://www.glassdoor.de/"`

Countries without a third tuple element in the `Country` enum are not supported and will raise an exception.

---

## Initialization Steps (per `scrape()` call)

### Step 1: Get CSRF Token
`_get_csrf_token()`:
- `GET {base_url}/Job/computer-science-jobs.htm`
- Regex: `r'"token":\s*"([^"]+)"'` on response HTML
- Sets `headers["gd-csrf-token"] = token`
- Falls back to `fallback_token` from `constant.py` if not found

### Step 2: Resolve Location
`_get_location(location, is_remote)`:
- If `location` is empty or `is_remote=True` → returns `("11047", "STATE")` (hardcoded remote location)
- Otherwise: `GET {base_url}/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={location}`
- Parses first result:
  - `locationId` → integer
  - `locationType`: `"C"` → `"CITY"`, `"S"` → `"STATE"`, `"N"` → `"COUNTRY"`
- Returns `(location_id: int, location_type: str)`
- 429 → logs and returns `(None, None)`, causing early exit

---

## Search Request (GraphQL)

**Endpoint**: `POST {base_url}/graph`

**Payload**: JSON array (single-element) with:
```json
[{
  "operationName": "JobSearchResultsQuery",
  "variables": { ... },
  "query": "<query_template>"
}]
```

Query template: `jobspy/glassdoor/constant.py` → `query_template`

**Variables built in `_add_payload()`**:

| Variable | Value |
|---|---|
| `keyword` | `scraper_input.search_term` |
| `locationId` | Resolved location ID (int) |
| `locationType` | `"CITY"`, `"STATE"`, or `"COUNTRY"` |
| `numJobsToShow` | `30` (hardcoded) |
| `pageNumber` | Current page number (1-indexed) |
| `pageCursor` | Cursor from previous page or `None` |
| `sort` | `"date"` (hardcoded) |
| `fromage` | `max(hours_old // 24, 1)` if `hours_old` set |
| `excludeJobListingIds` | `[]` (always empty) |
| `parameterUrlInput` | `"IL.0,12_I{location_type}{location_id}"` |
| `filterParams` | Array of filter objects (see below) |

---

## Filter Parameters (`filterParams` array)

Each filter is `{"filterKey": "<key>", "values": "<value>"}`:

| Filter | Key | Value |
|---|---|---|
| Easy apply | `"applicationType"` | `"1"` |
| Date range | `"fromAge"` | `str(max(hours_old // 24, 1))` |
| Job type | `"jobType"` | `scraper_input.job_type.value[0]` |

**Job type values** (from `JobType` enum `.value[0]`):

| `JobType` | Filter value |
|---|---|
| `FULL_TIME` | `"fulltime"` |
| `PART_TIME` | `"parttime"` |
| `CONTRACT` | `"contract"` |
| `INTERNSHIP` | `"internship"` |

Note: `is_remote` is handled by passing location_id `"11047"` with `location_type="STATE"` — not via a filter key.

---

## Pagination

- **Cursor-based** via `paginationCursors` array in the GraphQL response
- `jobspy/glassdoor/util.py` → `get_cursor_for_page(pagination_cursors, page_num)` extracts the cursor for the requested page number
- Page range: `range(range_start, range_end)` where `range_end = min(tot_pages, 31)`
- `tot_pages = (results_wanted // 30) + 2`
- Jobs processed in parallel: `ThreadPoolExecutor(max_workers=30)` per page

---

## Response Structure

```
response.json()[0]
  .data.jobListings.jobListings[]     → list of job data objects
  .data.jobListings.paginationCursors → cursor array for pagination
```

---

## Job Field Extraction (`_process_job(job_data)`)

### Job URL & ID
- `job_id = job_data["jobview"]["job"]["listingId"]`
- `job_url = "{base_url}job-listing/j?jl={job_id}"`
- `id = "gd-{job_id}"`
- Deduplication via `seen_urls` set

### Title
- `job["job"]["jobTitleText"]`

### Company Name
- `job["header"]["employerNameFromSearch"]`

### Company URL
- `"{base_url}Overview/W-EI_IE{company_id}.htm"` where `company_id = job["header"]["employer"]["id"]`

### Company Logo
- `job_data["jobview"]["overview"]["squareLogoUrl"]` (may be absent)

### Listing Type
- `job["header"]["adOrderSponsorshipLevel"].lower()` — e.g., `"sponsored"` or `"organic"`

### Date Posted
- `job["header"]["ageInDays"]` → `(datetime.now() - timedelta(days=age_in_days)).date()`
- `None` if `ageInDays` is absent

### Remote Status (`is_remote`)
- `job["header"]["locationType"] == "S"` → `is_remote = True`, `location = None`
- Otherwise: `is_remote = False`, location parsed from `locationName`

### Location
`jobspy/glassdoor/util.py` → `parse_location(location_name)`:
- Splits `locationName` by `", "` → `city, state` (first two parts)
- Returns `Location(city=city, state=state)`

### Compensation (`compensation`)
`jobspy/glassdoor/util.py` → `parse_compensation(job["header"])`:
- `payPeriod` → `CompensationInterval` mapping:
  | API value | Interval |
  |---|---|
  | `"ANNUAL"` | `YEARLY` |
  | `"MONTHLY"` | `MONTHLY` |
  | `"WEEKLY"` | `WEEKLY` |
  | `"DAILY"` | `DAILY` |
  | `"HOURLY"` | `HOURLY` |
- `payPeriodAdjustedPay["p10"]` → `min_amount`
- `payPeriodAdjustedPay["p90"]` → `max_amount`
- `payCurrency` → `currency`
- Returns `None` if `payPeriod` is absent

### Description (separate GraphQL call)
`_fetch_job_description(job_id)`:
- `POST {base_url}/graph` with `JobDetailQuery` (inline in `_fetch_job_description`)
- Query fetches `jobview.job.description`
- Converted per `description_format` (MARKDOWN → `markdown_converter()`)
- Uses bare `requests.post()` (not session) with current `headers`
- Returns `None` on non-200 response

### Emails
- `extract_emails_from_text(description)` on the fetched description

---

## Fields Summary

| Field | Source |
|---|---|
| `title` | `job.job.jobTitleText` |
| `company_name` | `job.header.employerNameFromSearch` |
| `company_url` | Constructed from `job.header.employer.id` |
| `company_logo` | `job.overview.squareLogoUrl` |
| `listing_type` | `job.header.adOrderSponsorshipLevel` |
| `date_posted` | `job.header.ageInDays` → relative date |
| `is_remote` | `job.header.locationType == "S"` |
| `location` | `job.header.locationName` (if not remote) |
| `compensation` | `job.header.payPeriod/payPeriodAdjustedPay/payCurrency` |
| `description` | Separate GraphQL `JobDetailQuery` call |
| `emails` | Regex on description |

---

## Concurrency

Jobs within a page are processed in parallel:
```python
with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
    future_to_job_data = {executor.submit(self._process_job, job): job for job in jobs_data}
```

Each `_process_job` call makes one additional HTTP request (description fetch). 30 jobs/page = up to 30 concurrent requests.

---

## Error Handling

- 429 from location AJAX → logs and returns `(None, None)` → `scrape()` returns empty `JobResponse`
- GraphQL response with `"errors"` key → raises `ValueError`, caught, returns empty page
- `requests.exceptions.ReadTimeout` → caught per page, returns empty page
- `_fetch_job_description()` wrapped in try/except → `None` on any exception
- Exception class: `GlassdoorException`

---

## Notes for AI Agents

- The CSRF token fetch hits `/Job/computer-science-jobs.htm` — if Glassdoor changes this page structure, the token extraction regex may break; `fallback_token` in `constant.py` is the safety net
- `is_remote` detection is structural (locationType field), not keyword-based — more reliable than LinkedIn/Google
- Glassdoor salary uses **percentile estimates** (`p10`/`p90`) not exact figures — these are statistical estimates
- `ageInDays` gives relative date, not absolute timestamp — date_posted shifts slightly per day
- The description fetch uses `requests.post()` directly (not the session object) — proxy rotation is bypassed for description fetches
- `country_indeed` parameter in `scrape_jobs()` maps to `ScraperInput.country` which is also used for Glassdoor domain selection
- Not all countries have Glassdoor support — `Country` entries without a third tuple value will raise an exception in `glassdoor_domain_value`
