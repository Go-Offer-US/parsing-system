# ZipRecruiter Scraper

**File**: `jobspy/ziprecruiter/__init__.py`
**Class**: `ZipRecruiter(Scraper)`
**Site enum**: `Site.ZIP_RECRUITER`
**Job ID prefix**: `"zr-{listing_key}"`

---

## Overview

ZipRecruiter is scraped via a **private mobile JSON API** (`api.ziprecruiter.com/jobs-app/jobs`). The scraper simulates a ZipRecruiter iPhone app session. Each job requires a second HTTP request to the listing page to fetch the full description and direct apply URL.

---

## HTTP Configuration

| Property | Value |
|---|---|
| Base URL | `https://www.ziprecruiter.com` |
| API URL | `https://api.ziprecruiter.com` |
| Session type | `TLSRotating` (default `is_tls=True`) — uses TLS fingerprinting |
| Rate limiting | `time.sleep(5)` between pages (skip on first page) |
| Headers | `jobspy/ziprecruiter/constant.py` → `headers` dict |

**Key headers** (from `constant.py`):
- `User-Agent`: simulates iPhone ZipRecruiter app (`"Job Search/87.0"`)
- `Authorization`: hardcoded `Basic` auth token
- `x-zr-zva-override`, `x-pushnotificationid`, `x-deviceid`: device simulation headers

---

## Session Initialization (`_get_cookies()`)

On `__init__`, before any search:
- `POST https://api.ziprecruiter.com/jobs-app/event` with `get_cookie_data` body (from `constant.py`)
- This establishes a session with device properties, setting required cookies

---

## Search Request

**Endpoint**: `GET https://api.ziprecruiter.com/jobs-app/jobs`

**Query parameters** built by `jobspy/ziprecruiter/util.py` → `add_params(scraper_input)`:

| Param | Value | Condition |
|---|---|---|
| `search` | `scraper_input.search_term` | Always |
| `location` | `scraper_input.location` | Always |
| `days` | `max(hours_old // 24, 1)` | If `hours_old` set |
| `employment_type` | `"full_time"` or `"part_time"` | If `job_type` is FULL_TIME or PART_TIME |
| `zipapply` | `1` | If `easy_apply` |
| `remote` | `1` | If `is_remote` |
| `radius` | `scraper_input.distance` | If `distance` set |
| `continue_from` | `continue_token` | Pagination (2nd page onward) |

**Job type mapping** (only FULL_TIME and PART_TIME are supported; other types fall back to `job_type.value[0]`):
```python
{JobType.FULL_TIME: "full_time", JobType.PART_TIME: "part_time"}
```

**Note**: ZipRecruiter only serves US and Canada jobs.

---

## Pagination

- **Cursor-based** — `continue` token from response feeds next request via `continue_from` param
- **20 jobs per page** (`jobs_per_page = 20`)
- Pages calculated upfront: `max_pages = ceil(results_wanted / 20)`
- Stops early if no jobs returned or no `continue_token`
- 5-second delay between pages (starting from page 2)

---

## Response Structure

```json
{
  "jobs": [...],
  "continue": "<next_cursor_token>"
}
```

Jobs are processed in parallel via `ThreadPoolExecutor(max_workers=20)` — one thread per job on the page.

---

## Job Field Extraction (`_process_job(job)`)

### Job URL & ID
- `job_url = "https://www.ziprecruiter.com/jobs//j?lvk={job['listing_key']}"`
- `id = "zr-{job['listing_key']}"`
- Deduplication via `seen_urls` set

### Title
- `job["name"]`

### Company Name
- `job["hiring_company"]["name"]`

### Location
- `city`: `job["job_city"]`
- `state`: `job["job_state"]`
- `country`: `Country.USA` if `job["job_country"] == "US"` else `Country.CANADA`

### Job Type (`job_type`)
`jobspy/ziprecruiter/util.py` → `get_job_type_enum(job_type_str)`:
- `job["employment_type"].replace("_", "").lower()` — e.g., `"full_time"` → `"fulltime"`
- Matched against all `JobType` enum tuple values
- Returns `list[JobType]` or `None`

### Compensation
From direct API response fields:
- `comp_interval`: `job["compensation_interval"]`; `"annual"` is remapped to `"yearly"`
- `comp_min`: `int(job["compensation_min"])` (if present)
- `comp_max`: `int(job["compensation_max"])` (if present)
- `comp_currency`: `job["compensation_currency"]`

Note: Stored as `Compensation(interval=comp_interval, ...)` — `interval` here is a raw string passed directly to `Compensation`, not a `CompensationInterval` enum value.

### Date Posted
- `job["posted_time"]` — ISO format string with trailing `"Z"` stripped
- `datetime.fromisoformat(posted_time.rstrip("Z")).date()`

### Description (from listing page — `_get_descr()`)
A second HTTP GET to `job_url` is made for every job:
1. Fetches `div.job_description` and `section.company_description`
2. Strips HTML attributes via `remove_attributes()`
3. Concatenates both sections as HTML string
4. Converted per `description_format` (MARKDOWN → `markdown_converter()`)
5. Falls back to `job["job_description"]` from API response if page fetch fails

### Direct Apply URL (`job_url_direct`)
Extracted from the listing page:
1. `soup.find("script", type="application/json")`
2. `json.loads(script.string)["model"]["saveJobURL"]`
3. Regex: `r"job_url=(.+)"` — extracts value after `job_url=`

### Remote Status
- **Not explicitly set** from the API response
- Not calculated in `_process_job()` — `is_remote` will be `None` unless derived via salary/description processing in the caller
- The `remote=1` search param filters results, but `is_remote` on the `JobPost` object is not populated

### Listing Type
- `job["buyer_type"]` — stored as `listing_type`

### Emails
- `extract_emails_from_text(description)` on the short `job["job_description"]` from API (not the full fetched description)

---

## Fields Summary

| Field | Source |
|---|---|
| `title` | `job.name` |
| `company_name` | `job.hiring_company.name` |
| `location` | `job.job_city/job_state/job_country` |
| `job_type` | `job.employment_type` matched to enum |
| `compensation` | `job.compensation_min/max/interval/currency` |
| `date_posted` | `job.posted_time` (ISO string) |
| `is_remote` | Not populated (None) |
| `description` | Fetched from listing page HTML |
| `job_url_direct` | Extracted from listing page JSON script |
| `listing_type` | `job.buyer_type` |
| `emails` | Regex on API description |

---

## Concurrency

Each page's jobs are processed in parallel:
```python
with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
    job_results = [executor.submit(self._process_job, job) for job in jobs_list]
```

This means up to 20 concurrent HTTP requests per page (description fetches). This is fast but increases the chance of triggering rate limits.

---

## Error Handling

- HTTP 429 → logs and returns partial results with empty continue token
- Non-200 responses → logged with response text; ZipRecruiter is noted as "likely not available in EU"
- Proxy errors logged as `"Indeed: Bad proxy"` (copy-paste bug in source — should say ZipRecruiter)
- `_get_descr()` exceptions are silently caught — falls back to API description
- Exception class: `ZipRecruiterException` (defined in `exception.py`)

---

## Notes for AI Agents

- ZipRecruiter is **US/Canada only** — `job_country` is always `"US"` or `"CA"` in responses
- The `is_remote` field on `JobPost` is `None` for ZipRecruiter results — the `remote=1` param filters at query time but the field is not set on the output object
- `compensation.interval` is a raw string (`"yearly"`, `"hourly"`, etc.), not a `CompensationInterval` enum — this differs from Indeed/Glassdoor
- Each job triggers one extra HTTP request (description fetch) — 20 jobs/page = 20 parallel requests
- The TLS session (`TLSRotating`) is critical — standard requests may be blocked without TLS fingerprint spoofing
- `employment_type` in the API uses underscore format (`"full_time"`) which is stripped before enum matching
- No support for CONTRACT, TEMPORARY, INTERNSHIP via `employment_type` param — only FULL_TIME and PART_TIME
