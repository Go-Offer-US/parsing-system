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
| Session type | `CurlCffiRotating` (`impersonate="chrome124"`) via `create_session(impersonate=...)` |
| Fallback session | `TLSRotating` (tls_client) if `curl_cffi` is not installed |
| Retry | No (curl_cffi session; retry was only for `RequestsRotating`) |
| Max results | Capped at 900 (`self.scraper_input.results_wanted = min(900, ...)`) |
| Jobs per page | 30 (`numJobsToShow: 30`) |
| Max pages | 30 |
| Headers | `jobspy/glassdoor/constant.py` → `headers` dict |

**Why curl_cffi?**  
Glassdoor is fronted by Cloudflare. Standard `requests` and even `tls_client` sessions are detected and receive a Cloudflare Managed Challenge (HTML page, status 403). `curl_cffi` uses libcurl compiled with BoringSSL — Chrome's actual TLS library — producing a JA3/HTTP2 fingerprint that Cloudflare cannot distinguish from a real browser.

Install: `pip install curl_cffi` or `pip install python-jobspy[cloudflare]`.  
Without it, the scraper falls back to `tls_client` with a warning, which may work on unprotected IPs.

**Key headers** (from `constant.py`):
- `gd-csrf-token`: set at runtime (fetched or fallback)
- `sec-ch-ua` and `user-agent` must match the same Chrome version to avoid bot detection fingerprint mismatch
- Standard browser headers (Accept, Origin, Referer, Sec-Fetch-*)

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
`_get_location(location)`:
- If `location` is empty → returns `("11047", "STATE")` (Glassdoor's worldwide/remote entity ID)
- Otherwise: `GET {base_url}/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={location}`
- Parses first result:
  - `locationId` → integer
  - `locationType`: `"C"` → `"CITY"`, `"S"` → `"STATE"`, `"N"` → `"COUNTRY"`
- Returns `(location_id: int, location_type: str)`

**Error handling in `_get_location()`**:
- `429` → logs error, returns `(None, None)` → `scrape()` returns empty `JobResponse`
- `400` / `403` (common from non-US IPs) → logs warning, falls back to `("11047", "STATE")`
- Any other non-200 → falls back to `("11047", "STATE")`

**Note**: `is_remote` is no longer passed to `_get_location()`. Remote filtering is handled exclusively via the `remoteWorkType` filter param in `_add_payload()`.

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

Each filter is `{"filterKey": "<key>", "values": "<value>"}` (all values are strings):

| Filter | Key | Value | Trigger |
|---|---|---|---|
| Easy apply | `"applicationType"` | `"1"` | `scraper_input.easy_apply` |
| Date range | `"fromAge"` | `str(days)` | `scraper_input.hours_old` |
| Remote work | `"remoteWorkType"` | `"1"` | `work_format=REMOTE` or `is_remote=True` |
| Seniority | `"seniorityType"` | see table below | `scraper_input.seniority_levels` |
| Job type | `"jobType"` | see table below | `scraper_input.job_type` |

**Seniority values** (`jobspy/glassdoor/util.py` → `GLASSDOOR_SENIORITY_VALUE`):

| `SeniorityLevel` | API value | Notes |
|---|---|---|
| `INTERNSHIP` | `"internship"` | |
| `ENTRY` | `"entrylevel"` | |
| `ASSOCIATE` | `"entrylevel"` | No distinct Glassdoor level, mapped to entry |
| `MID_SENIOR` | `"midseniorlevel"` | |
| `DIRECTOR` | `"director"` | |
| `EXECUTIVE` | `"executive"` | |

Only the **first** element of `seniority_levels` is used (Glassdoor API accepts one `seniorityType` value).

**Job type values** (from `JobType` enum `.value[0]`):

| `JobType` | Filter value |
|---|---|
| `FULL_TIME` | `"fulltime"` |
| `PART_TIME` | `"parttime"` |
| `CONTRACT` | `"contract"` |
| `INTERNSHIP` | `"internship"` |

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

**Partial error handling**: Glassdoor occasionally returns `"errors"` alongside valid job data (e.g., `jobsPageSeoData` DNS failure). The scraper checks whether `data.jobListings.jobListings` is present before raising — non-critical errors are logged as warnings and scraping continues.

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

### Remote / Work Format Detection

Remote status is determined from **two fields** in `job["header"]`:
- `locationType`: granularity of the job's location (`"C"` = city, `"S"` = state/region, `"N"` = country)
- `locationName`: human-readable location string (e.g., `"San Francisco, CA"`, `"Remote"`, `""`)

**Logic**:
```python
if location_name == "Remote" or (location_type == "S" and not location_name):
    is_remote = True
    work_format = WorkFormat.REMOTE
else:
    location = parse_location(location_name)
    work_format = None
```

**Why not just `locationType == "S"`?**  
State-level onsite jobs (e.g., "California, USA") also carry `locationType = "S"` with a non-empty `locationName`. Checking `locationName` prevents false-positive remote classification.

**`work_format = WorkFormat.ONSITE` for non-remote jobs** — Glassdoor API does not expose a hybrid/onsite distinction. Since both formats require physical office presence, all non-remote jobs are classified as `ONSITE`.

### Location
`jobspy/glassdoor/util.py` → `parse_location(location_name)`:
- Returns `None` if `location_name` is empty or `"Remote"`
- Otherwise splits by `", "` → `Location(city=city, state=state)`

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
- Returns `None` if `payPeriod` or `payPeriodAdjustedPay` is absent

### Description (separate GraphQL call)
`_fetch_job_description(job_id)`:
- `POST {base_url}/graph` with `JobDetailQuery` (inline query in the method)
- Uses **`self.session`** (curl_cffi) — same session as the main search, CSRF token and TLS fingerprint are reused
- Query fetches `jobview.job.description`
- Converted per `description_format` (MARKDOWN → `markdown_converter()`)
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
| `is_remote` | `locationName == "Remote"` or (`locationType == "S"` and empty name) |
| `work_format` | `WorkFormat.REMOTE` for remote; `WorkFormat.ONSITE` otherwise |
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

**Rate-limiting implication**: A single page scrape produces ~33 requests (1 CSRF + 1 location + 1 jobs page + 30 descriptions). Cloudflare may block the IP for ~20–40 seconds after a full page fetch. Avoid running multiple scraper instances against the same IP in rapid succession.

---

## Error Handling

| Condition | Behavior |
|---|---|
| `429` from location AJAX | Logs error, returns `(None, None)` → early exit with empty `JobResponse` |
| `400`/`403` from location AJAX | Logs warning, falls back to `("11047", "STATE")` worldwide location |
| GraphQL response with `"errors"` + missing job data | Raises `ValueError`, caught per page, returns empty page |
| GraphQL response with `"errors"` + job data present | Logs warning (non-critical), continues scraping |
| `requests.exceptions.ReadTimeout` | Caught per page, returns empty page |
| `_fetch_job_description()` failure | `description = None`, job still added |
| Exception class | `GlassdoorException` |

---

## Notes for AI Agents

- **Cloudflare bot detection**: The CSRF token page and `/graph` endpoint are both protected. `curl_cffi` with `impersonate="chrome124"` is required for reliable access. Without it, first requests may succeed but subsequent sessions get blocked. IP reputation also matters — residential/US proxies help.
- **CSRF token fallback**: `fallback_token` in `constant.py` is a hardcoded token that may expire. If scraping fails consistently with 403, update the fallback token by manually fetching a fresh one from `/Job/computer-science-jobs.htm`.
- **`sec-ch-ua` / `user-agent` version must match**: Chrome version in `sec-ch-ua` header must equal the version in `user-agent`. Mismatch triggers bot detection. Both currently set to Chrome 141.
- **`is_remote` detection is structural + name-based**, not keyword-based — more reliable than LinkedIn/Google. `locationType == "S"` alone is insufficient (state-wide onsite jobs share the same type).
- **`work_format` is always set**: Remote jobs get `WorkFormat.REMOTE`, all others get `WorkFormat.ONSITE`. Glassdoor API does not distinguish onsite from hybrid — both require office presence, so they are treated as equivalent.
- **Seniority filter uses first element only**: Glassdoor API accepts one `seniorityType` per query. Multi-level seniority filtering is not supported.
- **Salary uses percentile estimates**: `p10`/`p90` are statistical estimates from Glassdoor's salary database, not employer-reported values.
- **`ageInDays` is relative**: `date_posted` shifts by one day per calendar day. The same job scraped on different days will show different `date_posted`.
- **`country_indeed` parameter** in `scrape_jobs()` maps to `ScraperInput.country` which is also used for Glassdoor domain selection.
- Not all countries have Glassdoor support — `Country` entries without a third tuple value will raise an exception in `glassdoor_domain_value`.
