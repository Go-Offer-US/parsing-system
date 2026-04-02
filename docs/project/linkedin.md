# LinkedIn Scraper

**File**: `jobspy/linkedin/__init__.py`
**Class**: `LinkedIn(Scraper)`
**Site enum**: `Site.LINKEDIN`
**Job ID prefix**: `"li-{job_id}"`

---

## Overview

LinkedIn is scraped via its **public guest jobs API** (no authentication required). The scraper fetches HTML pages, parses them with BeautifulSoup, and optionally makes a second per-job request to retrieve full description and additional metadata.

---

## HTTP Configuration

| Property | Value |
|---|---|
| Base URL | `https://www.linkedin.com` |
| Session type | `RequestsRotating` (`is_tls=False`) |
| Retry | Yes (`has_retry=True`, `delay=5`) |
| Cookie clearing | Yes (`clear_cookies=True`) — cookies cleared before each request |
| Rate limiting | Random sleep between pages: `uniform(3, 7)` seconds |
| Headers | `jobspy/linkedin/constant.py` → `headers` dict (standard browser UA) |

---

## Search Request

**Endpoint**: `GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`

**Query parameters**:

| Param | Value | Notes |
|---|---|---|
| `keywords` | `scraper_input.search_term` | Job title / keywords |
| `location` | `scraper_input.location` | Location string |
| `distance` | `scraper_input.distance` | Radius in miles |
| `f_WT` | See work format codes below | Work type filter. `work_format` takes priority; `is_remote=True` fallback maps to `3` (Remote) |
| `f_E` | Comma-separated seniority codes | Seniority level filter; see codes below |
| `f_JT` | `job_type_code(job_type)` | See job type codes below |
| `f_AL` | `"true"` if `easy_apply` else omitted | Easy Apply filter |
| `f_C` | `"id1,id2,..."` | Comma-separated `linkedin_company_ids` |
| `f_TPR` | `"r{seconds}"` | Time filter: `hours_old * 3600` |
| `start` | `0, 25, 50, ...` | Pagination offset (increments by actual card count) |
| `pageNum` | Always `0` | Required but unused by LinkedIn |

**Work format codes** (`LINKEDIN_WORK_FORMAT_CODE` in `jobspy/linkedin/util.py`):

| `WorkFormat` | Code |
|---|---|
| `ONSITE` | `1` |
| `REMOTE` | `2` |
| `HYBRID` | `3` |

Note: `work_format` is a single value in `ScraperInput`. For multiple formats, make separate calls. `is_remote=True` (legacy) maps to `f_WT=3` (Remote) as backward-compatible fallback.

**Seniority codes** (`LINKEDIN_SENIORITY_CODE` in `jobspy/linkedin/util.py`):

| `SeniorityLevel` | Code |
|---|---|
| `INTERNSHIP` | `1` |
| `ENTRY` | `2` |
| `ASSOCIATE` | `3` |
| `MID_SENIOR` | `4` |
| `DIRECTOR` | `5` |
| `EXECUTIVE` | `6` |

Multiple values supported: `seniority_levels=["entry", "mid_senior"]` → `f_E=2,4`.

**Job type codes** (`jobspy/linkedin/util.py` → `job_type_code()`):

| `JobType` | Code |
|---|---|
| `FULL_TIME` | `"F"` |
| `PART_TIME` | `"P"` |
| `INTERNSHIP` | `"I"` |
| `CONTRACT` | `"C"` |
| `TEMPORARY` | `"T"` |

---

## Pagination

- **25 jobs per page** (`jobs_per_page = 25`)
- Start offset begins at `(scraper_input.offset // 10) * 10`
- After each page, `start += len(job_cards)` (not a fixed increment)
- **Hard cap**: stops when `start >= 1000` (LinkedIn API limit) or `results_wanted` is met
- Between pages: `time.sleep(random.uniform(3, 7))`

---

## Response Parsing

Response is HTML. Parsed with BeautifulSoup.

**Key CSS selectors** (search listing page):

| Data | Selector |
|---|---|
| Job card container | `div.base-search-card` |
| Job URL + ID | `a.base-card__full-link[href]` — job_id = last segment after final `-` in path |
| Job title | `span.sr-only` |
| Company name | `h4.base-search-card__subtitle > a` |
| Company URL | href from company `<a>` tag (query string stripped) |
| Location | `span.job-search-card__location` inside `div.base-search-card__metadata` |
| Date posted | `time.job-search-card__listdate[datetime]` or `time.job-search-card__listdate--new[datetime]` |
| Salary (if shown) | `span.job-search-card__salary-info` |

---

## Job Field Extraction (Listing Page)

### `work_format` and `is_remote`

`determine_work_format()` in `jobspy/linkedin/util.py` — priority chain:

1. **Search filter** (`scraper_input.work_format`): if set, all results are guaranteed to match → assigned directly to every job
2. **Detail page** (`parse_work_format_from_page()`): parses `h3[text="Work type"]` block — present only on some jobs
3. **Keyword fallback** (when `linkedin_use_keyword_work_format_fallback=True`): searches `title + description + location` for `"remote"` / `"wfh"` / `"hybrid"` — least accurate, can be disabled

`is_job_remote(work_format)` derives the `is_remote` bool: returns `True` only for `WorkFormat.REMOTE`.

`work_format` field stores one of: `WorkFormat.REMOTE`, `WorkFormat.HYBRID`, `WorkFormat.ONSITE`, or `None`.

### Compensation
- From `span.job-search-card__salary-info` text, e.g. `"$80,000 - $120,000"`
- Split on `"-"`, each part passed through `currency_parser()` (strips non-numeric, handles thousand separators)
- `currency`: first character of raw text if not `"$"`, otherwise `"USD"`
- No interval detected — stored without `CompensationInterval`

### Location
- Splits `span.job-search-card__location` text on `", "`
- 2 parts → `city, state`; 3 parts → `city, state, country`
- Country resolved via `Country.from_string()` (default: `"worldwide"`)

### Date Posted
- Parsed from `datetime` attribute of `<time>` tag: `"%Y-%m-%d"` format

---

## Per-Job Detail Request (`linkedin_fetch_description=True`)

When `scraper_input.linkedin_fetch_description` is `True`, a second GET request is made per job:

**URL**: `GET https://www.linkedin.com/jobs/view/{job_id}`

If LinkedIn redirects to `/signup`, the response is discarded and an empty dict returned.

**Fields extracted from detail page**:

### Description
- `div[class*="show-more-less-html__markup"]`
- HTML attributes stripped via `remove_attributes()`
- Converted per `description_format`: MARKDOWN → `markdown_converter()`, PLAIN → `plain_converter()`, HTML → as-is

### Job Type (`job_type`)
`jobspy/linkedin/util.py` → `parse_job_type(soup)`:
- Finds `h3.description__job-criteria-subheader` with text containing `"Employment type"`
- Gets next sibling `span.description__job-criteria-text.description__job-criteria-text--criteria`
- Lowercases, strips hyphens → passed to `get_enum_from_job_type()` → returns `list[JobType]`

### Job Level / Seniority (`job_level`)
`jobspy/linkedin/util.py` → `parse_job_level(soup)`:
- Finds `h3.description__job-criteria-subheader` with text containing `"Seniority level"`
- Gets next sibling span (same class as above)
- Returns raw string, e.g. `"Mid-Senior level"`, `"Entry level"`, `"Director"`
- Stored lowercased in `JobPost.job_level`

### Company Industry (`company_industry`)
`jobspy/linkedin/util.py` → `parse_company_industry(soup)`:
- Finds `h3.description__job-criteria-subheader` with text containing `"Industries"`
- Gets next sibling span
- Returns raw string, e.g. `"Software Development"`, `"Financial Services"`

### Job Function (`job_function`)
- Finds `h3` with text containing `"Job function"`
- Gets next `span.description__job-criteria-text`
- Returns string, e.g. `"Engineering"`, `"Information Technology"`

### Company Logo (`company_logo`)
- `img.artdeco-entity-image[data-delayed-url]`
- Returns the `data-delayed-url` attribute value (CDN URL)

### Direct Apply URL (`job_url_direct`)
- `code#applyUrl` element, decoded content
- Regex: `(?<=\?url=)[^"]+` — extracts URL after `?url=` parameter
- URL-decoded via `urllib.parse.unquote()`

---

## Fields Available per Mode

| Field | Without `linkedin_fetch_description` | With `linkedin_fetch_description` |
|---|---|---|
| `title` | Yes | Yes |
| `company_name` | Yes | Yes |
| `company_url` | Yes | Yes |
| `location` | Yes | Yes |
| `date_posted` | Yes | Yes |
| `compensation` | Yes (if shown in listing) | Yes |
| `is_remote` | Yes (title+location only) | Yes (title+location+description) |
| `description` | No | Yes |
| `job_type` | No | Yes |
| `job_level` | No | Yes |
| `company_industry` | No | Yes |
| `job_function` | No | Yes |
| `company_logo` | No | Yes |
| `job_url_direct` | No | Yes |
| `emails` | No | Yes (extracted from description) |

---

## Deduplication

`seen_ids: set` — tracks job IDs within a single `.scrape()` call. If the same `job_id` appears on multiple pages, it is skipped.

---

## Error Handling

- HTTP 429 → logs `"429 Response - Blocked by LinkedIn..."` and returns partial results
- Any HTTP error outside 200–399 → logs and returns partial results
- `"Proxy responded with"` in exception message → logs `"LinkedIn: Bad proxy"`
- Per-job exceptions wrapped as `LinkedInException` and re-raised
- Detail page returning a redirect to `/signup` → returns empty dict (guest API blocked)

---

## Notes for AI Agents

- `linkedin_fetch_description=True` doubles HTTP calls — use only when `job_level`, `job_type`, `description`, or `job_function` are needed
- The guest API at `/jobs-guest/...` is rate-limited; 429s are common at high volumes
- LinkedIn returns at most 1000 results for any query (API constraint, not a code limit)
- The `f_TPR` parameter takes **seconds**, not hours — always multiply `hours_old` by 3600
- Company IDs for `linkedin_company_ids` must be numeric LinkedIn company IDs (e.g., `1441` for Google)
- Location parsing assumes `"City, State"` or `"City, State, Country"` format — international locations may not parse cleanly
