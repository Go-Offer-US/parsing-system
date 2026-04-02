# Plan: LinkedIn Seniority Level Filter + Work Format

## Goal
1. Fix bug: `f_WT=2` currently sends "Hybrid" to LinkedIn when `is_remote=True` — should be `f_WT=3` (Remote)
2. Add `WorkFormat` enum and `work_format` field to `JobPost` (single value: Remote/Hybrid/Onsite)
3. Add `SeniorityLevel` enum and `seniority_levels` filter to `ScraperInput`
4. Improve work format detection: filter value → detail page parsing → keyword fallback (with flag)

## Files changed

| File | Why |
|---|---|
| `jobspy/model.py` | Add `WorkFormat`, `SeniorityLevel` enums; new fields in `JobPost` and `ScraperInput` |
| `jobspy/linkedin/util.py` | Add mappings, `parse_work_format_from_page()`, `determine_work_format()`, update `is_job_remote()` |
| `jobspy/linkedin/__init__.py` | Fix `f_WT` bug, add `f_E`, wire new util functions |
| `jobspy/__init__.py` | New params in `scrape_jobs()`, pipeline: work_format→string, is_remote sync |
| `jobspy/util.py` | Add `work_format` to `desired_order` |

## Steps

1. `model.py` — add enums and fields (others depend on this)
2. `linkedin/util.py` — add constants and functions
3. `linkedin/__init__.py` — fix bug, wire everything
4. `__init__.py` — surface new params, update pipeline
5. `util.py` — desired_order

## Backward compatibility

- `is_remote=True` in `scrape_jobs()` still works → maps to `f_WT=3` (Remote) via `elif`
- `work_format` defaults to `None` — existing callers unaffected
- `seniority_levels` defaults to `None`
- `is_remote` field in `JobPost` remains; synced from `work_format` when available
- Other scrapers (Indeed, Glassdoor, etc.) unaffected — they don't use new fields

## Risks
- `is_job_remote()` signature changes (internal LinkedIn-only function) — update all call sites
- `determine_work_format()` filter takes priority over detail page — if LinkedIn filter is buggy, all results inherit wrong format; acceptable tradeoff given block is often absent
