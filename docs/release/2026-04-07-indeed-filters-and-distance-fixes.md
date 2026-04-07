# Release: Indeed Filters, Distance Logic, Hybrid Guard

**Date:** 7 April 2026  
**Branch:** `feature/indeed`  
**Audience:** AI agents integrating with this customized JobSpy library

---

## Context

This release fixes several bugs in the Indeed scraper and introduces new behavior for `distance`, `work_format=hybrid`, and filter prioritization across Indeed and LinkedIn. All changes are **backwards-compatible** — existing call signatures continue to work with the same behavior, new parameters have safe defaults.

---

## Breaking changes

None.

---

## New parameters in `scrape_jobs()`

### `indeed_filter_priority: str = "date"`

**Problem:** Indeed's GraphQL API (`apis.indeed.com/graphql`) accepts only **one filter type per request**. The three mutually exclusive types are:

| Filter type | Activated by |
|---|---|
| `date` | `hours_old` is set |
| `composite` | `work_format` is set (remote/onsite) or `job_type` is set |
| `keyword` | `easy_apply=True` |

When both `hours_old` and `work_format`/`job_type` are set, only one can be sent. Sending both causes a `400 GRAPHQL_VALIDATION_FAILED` error from Indeed.

**New behavior:** `indeed_filter_priority` controls which filter wins when there is a conflict.

| Value | Behavior |
|---|---|
| `"date"` *(default)* | `hours_old` filter is sent; `work_format`/`job_type` filter is dropped |
| `"attributes"` | `work_format`/`job_type` filter is sent; `hours_old` is dropped |

When a filter is dropped, a `WARNING` is logged:
```
Indeed: work_format/job_type filter ignored — indeed_filter_priority='date' takes precedence (hours_old=24)
```

**Practical implication for AI agents:** If you call `scrape_jobs` with both `hours_old=24` and `work_format="remote"`, the default behavior applies `hours_old` and drops the API-level remote filter. Remote jobs are **still correctly identified** in the output via `is_job_remote()` parsing (attributes, location, description keywords) — they just are not pre-filtered on the API side. You may receive fewer remote results than `results_wanted` if the unfiltered feed contains many onsite jobs.

**Example usage:**
```python
# Default: hours_old wins (recommended for recency-focused scraping)
scrape_jobs(..., hours_old=24, work_format="remote")
# → date filter applied, work_format applied via post-processing only

# Override: work_format wins (when remote precision matters more than recency)
scrape_jobs(..., hours_old=24, work_format="remote", indeed_filter_priority="attributes")
# → DSQF7 composite filter applied, hours_old dropped
```

---

## Bug fixes

### 1. Indeed 400 error when `distance=None`

**Root cause:** When `distance` was not passed to `scrape_jobs()`, the Indeed GraphQL query contained `radius: None` — an invalid value for the required `Int!` field. Indeed returned `400 GRAPHQL_VALIDATION_FAILED`.

**Fix:** `_build_location_filter()` now defaults to `50` miles when `distance` is `None`:
```python
distance = self.scraper_input.distance or 50
```

**Note:** `radius` and `radiusUnit` are **required** fields in `JobSearchLocationInput`. They cannot be omitted even for remote searches. The remote filtering is handled separately via the `DSQF7` attribute key, not by omitting the radius.

---

### 2. `work_format` priority over `is_remote` flag in `is_remote_search`

**Root cause:** The `is_remote_search` property on `ScraperInput` was implemented as:
```python
return self.work_format == WorkFormat.REMOTE or self.is_remote
```
This meant `is_remote=True` overrode an explicit `work_format=WorkFormat.ONSITE`, producing a contradictory state.

**Fix:** `work_format` now takes priority when explicitly set:
```python
if self.work_format is not None:
    return self.work_format == WorkFormat.REMOTE
return self.is_remote
```

**Impact:** Passing `work_format="onsite"` now correctly suppresses remote filtering even if `is_remote=True` is also passed. This is the expected behavior — explicit `work_format` always wins.

---

### 3. LinkedIn: `distance` not sent for remote searches

**New behavior:** When `is_remote_search` is `True` (i.e., `work_format="remote"` or `is_remote=True`), LinkedIn's `distance` parameter is forced to `None` and omitted from the request. LinkedIn already handles remote jobs globally — the distance parameter has no effect on remote results and its presence can cause unexpected geographic filtering.

This is transparent to callers: pass `distance` as usual, it will be applied for onsite/hybrid searches and silently ignored for remote.

---

## New guard: `work_format="hybrid"` skips unsupported sites

**New behavior:** `work_format="hybrid"` is only natively supported by **LinkedIn**. When other sites are included in `site_name` alongside `work_format="hybrid"`, they are **silently skipped** before scraping begins.

A `WARNING` is emitted:
```
work_format='hybrid' is only supported by ['linkedin']. Skipping: ['indeed', 'glassdoor']
```

The returned DataFrame will only contain LinkedIn results.

**Supported sites per `work_format`:**

| work_format | LinkedIn | Indeed | Glassdoor | Others |
|---|---|---|---|---|
| `remote` | ✅ | ✅ | ✅ | ✅ |
| `onsite` | ✅ | ✅ | ✅ | ✅ |
| `hybrid` | ✅ | ❌ skipped | ❌ skipped | ❌ skipped |

**Important for AI agents:** Do not call `scrape_jobs(site_name=["linkedin", "indeed"], work_format="hybrid")` expecting Indeed results — they will not come back. For hybrid searches, only LinkedIn data is available. This is an API limitation, not a library bug.

---

## `ScraperInput` model changes

New fields added to `jobspy.model.ScraperInput`:

| Field | Type | Default | Description |
|---|---|---|---|
| `indeed_filter_priority` | `str` | `"date"` | Controls which Indeed filter wins when both `hours_old` and attributes conflict. Values: `"date"` or `"attributes"` |

New property on `ScraperInput`:

| Property | Returns | Logic |
|---|---|---|
| `is_remote_search` | `bool` | `True` if `work_format == REMOTE`; if `work_format` is `None`, falls back to `is_remote` flag |

---

## Test coverage added

| File | Type | What it covers |
|---|---|---|
| `tests/unit/test_indeed_filters.py` | Unit | `_build_filters()` output for all parameter combinations: date-only, composite-only, priority conflicts, easy_apply |
| `tests/unit/test_unsupported_hybrid_search.py` | Unit | Hybrid site filtering, `ScraperInput` construction, `is_remote_search` property |
| `tests/integration/test_multiple_source.py` | Integration | Multi-source scraping (LinkedIn + Indeed + Glassdoor) with remote/onsite/hybrid work formats using prod-like parameters |

Run unit tests:
```bash
pytest tests/unit/ -v
```

Run integration tests (requires live network, optional `PROXY` env var):
```bash
PROXY=http://user:pass@host:port pytest tests/integration/test_multiple_source.py -v -m integration
```

---

## Summary for AI agents

When calling `scrape_jobs()` in production:

1. **`hours_old` + `work_format` conflict on Indeed** — default behavior keeps `hours_old`. Remote vac detection still works via parsing. If you need API-level remote filtering, pass `indeed_filter_priority="attributes"` and drop `hours_old`.

2. **Always pass `distance`** — omitting it causes a 400 from Indeed. Default is `50` miles (applied automatically if `None`).

3. **`work_format="hybrid"` → only LinkedIn runs** — don't expect results from other sites.

4. **`work_format` overrides `is_remote`** — if you pass `work_format="onsite"`, `is_remote=True` is ignored.
