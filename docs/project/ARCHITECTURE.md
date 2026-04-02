# JobSpy — Project Architecture

> Target audience: AI agents writing code in this codebase. This document describes structure, entry points, data flow, and conventions so you can navigate and extend the project without prior context.

---

## Directory Layout

```
JobSpy/
├── jobspy/                        # Main library package
│   ├── __init__.py                # Public API — scrape_jobs() lives here
│   ├── model.py                   # All Pydantic models and enums (JobPost, ScraperInput, etc.)
│   ├── util.py                    # Shared utilities: sessions, salary parsing, logging, converters
│   ├── exception.py               # Per-scraper custom exceptions
│   │
│   ├── linkedin/
│   │   ├── __init__.py            # LinkedIn scraper class
│   │   ├── util.py                # LinkedIn-specific parsers (job_type, job_level, industry, remote)
│   │   └── constant.py            # HTTP headers
│   │
│   ├── indeed/
│   │   ├── __init__.py            # Indeed scraper class
│   │   ├── util.py                # Indeed-specific parsers (job_type, compensation, remote)
│   │   └── constant.py            # HTTP headers + GraphQL query template
│   │
│   ├── ziprecruiter/
│   │   ├── __init__.py            # ZipRecruiter scraper class
│   │   ├── util.py                # ZipRecruiter-specific helpers (params builder, job_type)
│   │   └── constant.py            # HTTP headers + cookie data
│   │
│   ├── glassdoor/
│   │   ├── __init__.py            # Glassdoor scraper class
│   │   ├── util.py                # Glassdoor-specific parsers (compensation, location, cursor)
│   │   └── constant.py            # HTTP headers + GraphQL query template + fallback CSRF token
│   │
│   ├── google/
│   │   ├── __init__.py            # Google Jobs scraper class
│   │   ├── util.py                # Google-specific raw JSON extractors
│   │   └── constant.py            # HTTP headers + async_param constant
│   │
│   ├── naukri/                    # Indian job board (out of scope for this doc set)
│   ├── bdjobs/                    # Bangladesh job board (out of scope)
│   └── bayt/                      # Middle East job board (out of scope)
│
├── docs/
│   ├── project/                   # AI-targeted documentation (this folder)
│   ├── dev/
│   ├── release/
│   └── tasks/
│
├── tests/                         # Test suite
├── pyproject.toml                 # Poetry project definition
└── README.md
```

---

## Core Concepts

### Entry Point: `scrape_jobs()`

`jobspy/__init__.py` → `scrape_jobs()` is the **only public function** users call.

```python
from jobspy import scrape_jobs
df = scrape_jobs(
    site_name=["linkedin", "indeed"],
    search_term="software engineer",
    location="San Francisco, CA",
    results_wanted=50,
)
```

Internal flow:
1. Parse `site_name` → list of `Site` enum values
2. Build a single `ScraperInput` Pydantic model shared across all scrapers
3. Instantiate one scraper per site, run all in parallel via `ThreadPoolExecutor`
4. Each scraper returns `JobResponse(jobs=[JobPost, ...])`
5. Flatten all `JobPost` objects into dicts, process salary/location/job_type
6. Build and return a `pandas.DataFrame` with a canonical column order (`desired_order` in `util.py`)

### Scraper Base Class

`jobspy/model.py` → `class Scraper(ABC)`

Every scraper inherits from this. Required interface:
```python
class Scraper(ABC):
    def __init__(self, site: Site, proxies, ca_cert, user_agent): ...
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...  # must implement
```

Constructor signature for all scrapers (all kwargs, always passed from `scrape_jobs`):
```python
def __init__(self, proxies=None, ca_cert=None, user_agent=None)
```

### ScraperInput — The Shared Filter Object

Defined in `jobspy/model.py`. One instance is created per `scrape_jobs()` call and passed into every scraper's `.scrape()` method.

| Field | Type | Description |
|---|---|---|
| `site_type` | `list[Site]` | Which boards to scrape |
| `search_term` | `str \| None` | Job title / keywords |
| `google_search_term` | `str \| None` | Overrides query building for Google only |
| `location` | `str \| None` | City, state, or country string |
| `country` | `Country` | Enum; used by Indeed/Glassdoor for domain selection (default: USA) |
| `distance` | `int \| None` | Radius in miles |
| `is_remote` | `bool` | Filter remote jobs |
| `job_type` | `JobType \| None` | Enum: FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP, etc. |
| `easy_apply` | `bool \| None` | Filter to one-click apply jobs |
| `offset` | `int` | Pagination offset for results |
| `results_wanted` | `int` | Target number of results (default 15) |
| `hours_old` | `int \| None` | Only jobs posted within N hours |
| `linkedin_fetch_description` | `bool` | LinkedIn: fetch full description + details via extra HTTP call |
| `linkedin_company_ids` | `list[int] \| None` | LinkedIn: filter by company |
| `description_format` | `DescriptionFormat` | MARKDOWN (default), HTML, or PLAIN |
| `request_timeout` | `int` | Seconds before HTTP timeout (default 60) |

---

## Data Models (`jobspy/model.py`)

### JobPost
The canonical output unit. All scrapers produce `list[JobPost]`.

```python
class JobPost(BaseModel):
    id: str | None                  # Prefixed: "li-", "in-", "zr-", "gd-", "go-"
    title: str
    company_name: str | None
    job_url: str                    # Canonical listing URL on the source site
    job_url_direct: str | None      # Direct employer application URL (if available)
    location: Location | None
    description: str | None         # Formatted per description_format
    company_url: str | None         # Company profile page on the source site
    company_url_direct: str | None  # Company's own website
    job_type: list[JobType] | None
    compensation: Compensation | None
    date_posted: date | None
    emails: list[str] | None        # Extracted from description via regex
    is_remote: bool | None
    listing_type: str | None        # e.g., sponsorship level from Glassdoor
    # LinkedIn-specific
    job_level: str | None           # e.g., "mid-senior level", "entry level"
    job_function: str | None        # e.g., "Engineering", "Sales"
    # LinkedIn + Indeed
    company_industry: str | None
    # Indeed-specific
    company_addresses: str | None
    company_num_employees: str | None
    company_revenue: str | None
    company_description: str | None
    company_logo: str | None
    banner_photo_url: str | None
    # Naukri-specific (will be None for all other scrapers)
    skills: list[str] | None
    experience_range: str | None
    company_rating: float | None
    company_reviews_count: int | None
    vacancy_count: int | None
    work_from_home_type: str | None
```

### Key Enums

**`Site`** — identifies which scraper:
```
LINKEDIN, INDEED, ZIP_RECRUITER, GLASSDOOR, GOOGLE, BAYT, NAUKRI, BDJOBS
```

**`JobType`** — multilingual; matching is done against all tuple values:
```
FULL_TIME, PART_TIME, CONTRACT, TEMPORARY, INTERNSHIP,
PER_DIEM, NIGHTS, OTHER, SUMMER, VOLUNTEER
```
Matching helper: `get_enum_from_job_type(str)` in `util.py` — strips hyphens/spaces, lowercases, then checks all enum tuple values.

**`CompensationInterval`**:
```
YEARLY, MONTHLY, WEEKLY, DAILY, HOURLY
```

**`DescriptionFormat`**:
```
MARKDOWN (default), HTML, PLAIN
```

**`Country`** — 90+ countries. Key properties:
- `.indeed_domain_value` → `(subdomain, api_country_code)` tuple
- `.glassdoor_domain_value` → glassdoor hostname
- `.get_glassdoor_url()` → full base URL
- `Country.from_string("usa")` → `Country.USA`

---

## HTTP Session Architecture (`jobspy/util.py`)

Two session types, both support proxy rotation:

### `TLSRotating` (default for ZipRecruiter)
- Extends `tls_client.Session`
- `random_tls_extension_order=True` — randomizes TLS fingerprint to evade bot detection
- Proxies cycled on every request via `itertools.cycle`

### `RequestsRotating` (used by LinkedIn, Indeed, Glassdoor, Google)
- Extends `requests.Session`
- Optional retry via `urllib3.util.retry.Retry` (3 retries, status codes: 500, 502, 503, 504, 429)
- Optional cookie clearing per request (`clear_cookies=True`)
- Proxies cycled on every request

### `create_session()` factory
```python
create_session(
    proxies=...,      # str | list[str] | None
    ca_cert=...,      # path to CA cert
    is_tls=True,      # True → TLSRotating, False → RequestsRotating
    has_retry=False,  # enable retry adapter
    delay=1,          # backoff_factor for retry
    clear_cookies=False,
)
```

---

## Salary Processing Pipeline

### Direct salary data (LinkedIn, Indeed, ZipRecruiter, Glassdoor)
1. Scraper extracts structured salary → sets `compensation: Compensation`
2. In `scrape_jobs()`: flattened into `interval`, `min_amount`, `max_amount`, `currency`
3. `salary_source = "direct_data"`

### Salary from description (USA only, fallback)
1. `extract_salary(description)` in `util.py` runs regex:
   ```
   \$(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)\s*[-—–]\s*(?:\$)?(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)
   ```
2. Determines interval by magnitude:
   - `< 350` → HOURLY
   - `< 30,000` → MONTHLY
   - `>= 30,000` → YEARLY
3. Validates range within `[1,000, 700,000]`
4. `salary_source = "description"`

### `enforce_annual_salary=True`
Converts all intervals to yearly:
- HOURLY × 2080
- MONTHLY × 12
- WEEKLY × 52
- DAILY × 260

---

## Output DataFrame

Column order is fixed by `desired_order` in `util.py`:

```
id, site, job_url, job_url_direct, title, company, location, date_posted,
job_type, salary_source, interval, min_amount, max_amount, currency,
is_remote, job_level, job_function, listing_type, emails, description,
company_industry, company_url, company_logo, company_url_direct,
company_addresses, company_num_employees, company_revenue, company_description,
skills, experience_range, company_rating, company_reviews_count,
vacancy_count, work_from_home_type
```

Sorted by `[site ASC, date_posted DESC]`. All-NA columns are dropped before concatenation.

---

## Error Handling

- Each scraper has a dedicated exception class in `jobspy/exception.py`:
  `LinkedInException`, `IndeedException`, `ZipRecruiterException`, `GlassdoorException`, `GoogleJobsException`
- Scrapers log errors and return partial `JobResponse` on failure — they do not crash the whole `scrape_jobs()` call
- HTTP 429 is handled explicitly with a specific log message in each scraper
- `ThreadPoolExecutor` in `scrape_jobs()` collects results via `as_completed()`; a failing future still allows other scrapers to complete

---

## Adding a New Scraper

1. Create `jobspy/<name>/` with `__init__.py`, `util.py`, `constant.py`
2. Implement class inheriting `Scraper`, implement `scrape(scraper_input) -> JobResponse`
3. Add `Site.<NAME> = "<name>"` to `Site` enum in `model.py`
4. Add `Site.<NAME>: <ClassName>` to `SCRAPER_MAPPING` in `jobspy/__init__.py`
5. Add `<Name>Exception` to `exception.py`
6. Import the class in `jobspy/__init__.py`

---

## Conventions

- Job IDs are prefixed strings: `"li-{id}"`, `"in-{id}"`, `"zr-{id}"`, `"gd-{id}"`, `"go-{id}"`
- `seen_urls: set` deduplicates within a single scrape run
- Descriptions default to Markdown via `markdownify`; pass `description_format="html"` or `"plain"` to change
- `is_remote` detection always checks for: `"remote"`, `"work from home"`, `"wfh"` (case-insensitive)
- `company_industry` strings are normalized: `.replace("Iv1", "").replace("_", " ").title().strip()`
- Pagination varies by scraper: offset-based (LinkedIn), cursor-based (Indeed, ZipRecruiter, Glassdoor, Google)
