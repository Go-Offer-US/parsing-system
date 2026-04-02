# Google Jobs Scraper

**File**: `jobspy/google/__init__.py`
**Class**: `Google(Scraper)`
**Site enum**: `Site.GOOGLE`
**Job ID prefix**: `"go-{job_info[28]}"`

---

## Overview

Google Jobs is scraped via **Google Search** with the `udm=8` parameter (Jobs mode). Unlike other scrapers, there is no official or private API — the scraper parses Google's search result HTML and embedded JSON payloads. Pagination uses a cursor extracted from HTML attributes.

This scraper provides the least structured data: no compensation, no company URL, no job_type from API — these are inferred from description text.

---

## HTTP Configuration

| Property | Value |
|---|---|
| Search URL | `https://www.google.com/search` |
| Pagination URL | `https://www.google.com/async/callback:550` |
| Session type | `RequestsRotating` (`is_tls=False`, `has_retry=True`) |
| Retry | Yes |
| Max results | Capped at 900 |
| Jobs per page | 10 |
| Headers | Two header sets: `headers_initial` (search), `headers_jobs` (pagination) — from `constant.py` |

---

## Query Construction (`_get_initial_cursor_and_jobs()`)

The search query is built as a plain text string. Base: `"{search_term} jobs"`

Filters appended as text phrases in this order:

### Job Type
```python
{
    JobType.FULL_TIME: "Full time",
    JobType.PART_TIME: "Part time",
    JobType.INTERNSHIP: "Internship",
    JobType.CONTRACT: "Contract",
}
```
Appended directly: `query += f" {job_type_text}"`

**Only these four job types are supported.** Other `JobType` values are silently ignored.

### Location
```python
query += f" near {location}"
```

### Time Filter
| `hours_old` | Appended phrase |
|---|---|
| `<= 24` | `"since yesterday"` |
| `<= 72` | `"in the last 3 days"` |
| `<= 168` | `"in the last week"` |
| `> 168` | `"in the last month"` |

### Remote
```python
query += " remote"
```

### `google_search_term` Override
If `scraper_input.google_search_term` is set, it **completely replaces** the constructed query. All other filters above are ignored.

---

## Initial Request

`GET https://www.google.com/search?q={query}&udm=8`

Using `headers_initial` from `constant.py`.

**From the response HTML, two things are extracted**:

1. **Forward cursor** (for pagination):
   - Regex: `r'<div jsname="Yust4d"[^>]+data-async-fc="([^"]+)"'`
   - Extracts `data-async-fc` attribute value
   - If not found → returns `None`, scraper returns only initial page results (≤10 jobs) with a warning log

2. **Job data** (initial page):
   - `jobspy/google/util.py` → `find_job_info_initial_page(response.text)`
   - Uses regex pattern `520084652":([...]` to extract embedded JSON array from page source
   - Returns list of raw job info arrays

---

## Pagination Request

`GET https://www.google.com/async/callback:550?fc={cursor}&fcv=3&async={async_param}`

Using `headers_jobs` from `constant.py`. `async_param` is a constant from `constant.py`.

**Response parsing** (`_parse_jobs(response_text)`):
1. Find `[[[` ... `]]]` boundaries in response text
2. `json.loads(s)[0]` → list of `[_, job_data_str]` pairs
3. For each pair: if `job_data_str` starts with `"[[["`, parse as JSON and pass to `find_job_info()` (from `util.py`)
4. Extract next forward cursor from same regex pattern as initial page

---

## Raw Job Data Structure

Jobs are represented as **positional arrays**, not named objects. Indices used:

| Index | Field |
|---|---|
| `[0]` | Job title |
| `[1]` | Company name |
| `[2]` | Location string (e.g., `"San Francisco, CA, USA"`) |
| `[3][0][0]` | Job URL (source listing URL) |
| `[12]` | Days ago string (e.g., `"3 days ago"`) |
| `[19]` | Job description (plain text) |
| `[28]` | Job ID (used as unique identifier) |

**Important**: The indices are reverse-engineered from Google's internal data structure and may break if Google changes their format.

---

## Job Field Extraction (`_parse_job(job_info)`)

### Job URL & ID
- `job_url = job_info[3][0][0]`
- `id = "go-{job_info[28]}"`
- Deduplication via `seen_urls` set

### Title
- `job_info[0]`

### Company Name
- `job_info[1]`

### Location
- `job_info[2]` — raw string, e.g., `"New York, NY, USA"`
- Split on `","`:
  - First part → `city`
  - Second part → `state`
  - Remaining → `country` (first element of remainder list)

### Date Posted
- `job_info[12]` — string like `"3 days ago"`, `"Posted 5 days ago"`, `"Just posted"`
- Regex `r"\d+"` extracts the numeric part
- `date_posted = (datetime.now() - timedelta(days=days_ago)).date()`
- If no number found → `date_posted = None`
- `"Just posted"` → `None` (no number to extract)

### Description
- `job_info[19]` — plain text (not HTML)
- Used as-is (no conversion needed, already plain text)

### Remote Status (`is_remote`)
- `"remote" in description.lower() or "wfh" in description.lower()`
- Keyword-based, from description text only

### Job Type (`job_type`)
`jobspy/util.py` → `extract_job_type(description)`:
- Regex patterns on description text:
  | Pattern | `JobType` |
  |---|---|
  | `r"full\s?time"` | `FULL_TIME` |
  | `r"part\s?time"` | `PART_TIME` |
  | `r"internship"` | `INTERNSHIP` |
  | `r"contract"` | `CONTRACT` |
- Returns `list[JobType]` (can match multiple) or `None` if no match

### Emails
- `extract_emails_from_text(description)` — regex on plain text description

---

## Fields Summary

| Field | Source | Notes |
|---|---|---|
| `title` | `job_info[0]` | Direct |
| `company_name` | `job_info[1]` | Direct |
| `location` | `job_info[2]` | Parsed by splitting on `","` |
| `job_url` | `job_info[3][0][0]` | Link to source listing |
| `date_posted` | `job_info[12]` | Relative string → date |
| `description` | `job_info[19]` | Plain text |
| `is_remote` | Description keywords | Not structural |
| `job_type` | Description regex | Not structural |
| `emails` | Description regex | — |
| `compensation` | **Not available** | Always `None` |
| `company_url` | **Not available** | Always `None` |
| `job_level` | **Not available** | Always `None` |
| `company_industry` | **Not available** | Always `None` |
| `job_url_direct` | **Not available** | Always `None` |

---

## Pagination Flow

```
Initial GET /search?q=...&udm=8
  → jobs (≤10) + forward_cursor

Loop while seen_urls < results_wanted + offset and forward_cursor:
  GET /async/callback:550?fc={cursor}&fcv=3&async=...
    → jobs (≤10) + next_forward_cursor
```

If `forward_cursor` is `None` after the initial request (≤10 results or Google blocked), the loop doesn't run and only initial results are returned.

---

## Error Handling

- No forward cursor found → `log.warning(...)`, returns initial jobs only
- Page fetch exception → `log.error(...)`, breaks pagination loop
- No jobs on page → `log.info(...)`, breaks loop
- No retry within `_get_jobs_next_page()` — failures stop pagination silently
- Exception class: `GoogleJobsException` (defined in `exception.py`)

---

## Notes for AI Agents

- Google is the **least reliable** scraper — structure depends on reverse-engineered JSON indices that can change without notice
- `google_search_term` overrides all filter logic — use it for advanced queries (e.g., site-specific searches, Boolean operators)
- Compensation data is **never available** from Google Jobs — salary_source will always be either `"description"` (if parsed from text) or `None`
- `job_type` is inferred from description text, not from structured data — expect lower accuracy than Indeed/ZipRecruiter
- `is_remote` checks description only (`"remote"` or `"wfh"`) — no structural signal like Glassdoor's `locationType`
- The `udm=8` parameter switches Google Search into Jobs mode — without it, regular web results are returned
- The `async_param` constant in `constant.py` is a required parameter for pagination requests and must not be changed
- `description` is plain text (not HTML) — `markdown_converter` and `plain_converter` are not applied
- Date parsing fails silently on `"Just posted"` and similar strings without numbers — `date_posted` will be `None`
- The `data-async-fc` cursor in HTML is base64-like encoded and opaque — treat as a black-box token
