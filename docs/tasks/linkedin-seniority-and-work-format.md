# ТЗ: Seniority Level Filter + Work Format (Hybrid/Onsite/Remote)

**Статус**: Готово к разработке
**Приоритет**: Высокий
**Скоуп итерации**: LinkedIn. Остальные источники — совместимая архитектура без реализации.

---

## Анализ текущего состояния по всем источникам

Перед проектированием — аудит того, что есть и что возможно в каждом скрапере.

### Work Format (Remote / Hybrid / Onsite)

| Источник | Фильтр запроса | Структурные данные в ответе | Текущая реализация |
|---|---|---|---|
| **LinkedIn** | `f_WT=1/2/3` (надёжно) | `h3[Work type]` на detail page (присутствует не всегда) | `f_WT=2` + keyword — **баг**: `f_WT=2` это Hybrid, не Remote |
| **Indeed** | `DSQF7` key = Remote (только Remote, без Hybrid) | `job.attributes[].label` — может содержать "Remote" | `is_job_remote()` по keywords в attributes + description + location |
| **Glassdoor** | Нет явного фильтра | `locationType == "S"` = Remote (binary, нет Hybrid) | `if locationType == "S": is_remote = True` |
| **ZipRecruiter** | `remote=1` (только Remote) | Нет в API-ответе | `is_remote` не заполняется вообще (`None`) |
| **Google** | Текстом в запросе (`"remote"`) | Нет структурных данных | Keyword по description |

### Seniority Level

| Источник | Фильтр запроса | Структурные данные в ответе | Текущая реализация |
|---|---|---|---|
| **LinkedIn** | `f_E=1..6` (надёжно) | `h3[Seniority level]` на detail page | Нет фильтра; `job_level` парсится как raw string |
| **Indeed** | Нет | Нет в GraphQL-ответе | Нет |
| **Glassdoor** | Нет | Нет | Нет |
| **ZipRecruiter** | Нет | Нет | Нет |
| **Google** | Нет | Нет | Нет |

---

## Баги в текущем коде

### Баг 1: `f_WT=2` означает Hybrid, не Remote

**Файл**: `jobspy/linkedin/__init__.py:99`

```python
# Текущий код — НЕВЕРНО:
"f_WT": 2 if scraper_input.is_remote else None,
```

Правильный маппинг LinkedIn `f_WT`:
- `1` = On-site
- `2` = **Hybrid** ← сейчас передаётся для remote-фильтрации
- `3` = Remote

### Баг 2: `is_job_remote()` не различает Remote/Hybrid/Onsite

**Файл**: `jobspy/linkedin/util.py:88`

Keyword-поиск даёт false positives ("Remote City, TX") и false negatives (remote-вакансия без слова "remote" в описании). Не позволяет хранить Hybrid как отдельное значение.

---

## Проектирование: унифицированная схема данных

### Принципы

1. **LinkedIn — эталон** для значений enum. Остальные источники маппятся на него.
2. **`work_format` в `JobPost` — одно значение** (не список): одна вакансия = один формат работы.
3. **Фильтр `work_format` в `ScraperInput` — одно значение**, не список. Причина: если передать одно значение (например `REMOTE`), LinkedIn гарантированно возвращает только Remote-вакансии — можно проставить `work_format=REMOTE` каждой вакансии без парсинга. Если передать несколько значений, результаты смешиваются и нельзя гарантированно определить формат конкретной вакансии (блок `Work type` на detail page присутствует не всегда). Для разных форматов — делать отдельные запросы.
4. **`seniority_levels` в `ScraperInput` — список.** Для seniority это ОК: LinkedIn `f_E=2,3` сужает пул, но каждая вакансия сохраняет свой уровень на detail page. Нас интересует фильтрация пула, а не вывод уровня из фильтра.
5. **`is_remote` остаётся** в `JobPost` для обратной совместимости — вычисляется из `work_format`.
6. **`SeniorityLevel` использует строковые значения** enum (не числовые) — числа LinkedIn хранятся только в маппинге внутри LinkedIn-скрапера, чтобы остальные источники могли маппить свои значения независимо.

---

### Изменение 1: Новые enum в `jobspy/model.py`

```python
class WorkFormat(Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class SeniorityLevel(Enum):
    INTERNSHIP = "internship"
    ENTRY = "entry"
    ASSOCIATE = "associate"
    MID_SENIOR = "mid_senior"
    DIRECTOR = "director"
    EXECUTIVE = "executive"
```

**Почему строковые значения у `SeniorityLevel`**: Indeed/Glassdoor/ZipRecruiter в будущем могут иметь свои термины ("Senior", "Lead", "Principal"). Строковые значения позволяют маппить любой источник на этот enum без привязки к числам LinkedIn.

Маппинг числовых кодов LinkedIn хранится **только** в `jobspy/linkedin/util.py`:
```python
LINKEDIN_SENIORITY_CODE = {
    SeniorityLevel.INTERNSHIP: 1,
    SeniorityLevel.ENTRY: 2,
    SeniorityLevel.ASSOCIATE: 3,
    SeniorityLevel.MID_SENIOR: 4,
    SeniorityLevel.DIRECTOR: 5,
    SeniorityLevel.EXECUTIVE: 6,
}

LINKEDIN_WORK_FORMAT_CODE = {
    WorkFormat.ONSITE: 1,
    WorkFormat.REMOTE: 2,
    WorkFormat.HYBRID: 3,
}
```

---

### Изменение 2: Обновить `JobPost` в `jobspy/model.py`

```python
class JobPost(BaseModel):
    ...
    is_remote: bool | None = None          # оставить — вычисляется из work_format
    work_format: WorkFormat | None = None  # новое поле: одно значение
    ...
```

`is_remote` вычисляется в `scrape_jobs()` автоматически:
```python
# При сборке DataFrame:
if job_data.get("work_format") is not None:
    job_data["is_remote"] = (job_data["work_format"] == WorkFormat.REMOTE.value)
```

---

### Изменение 3: Обновить `ScraperInput` в `jobspy/model.py`

```python
class ScraperInput(BaseModel):
    ...
    work_format: WorkFormat | None = None              # фильтр: одно значение
    seniority_levels: list[SeniorityLevel] | None = None  # фильтр: [ENTRY, MID_SENIOR]
    ...
```

**Почему `work_format` — одно значение**: при одном значении фильтра LinkedIn гарантированно возвращает только вакансии этого формата → можно проставить `work_format` каждой вакансии без дополнительного парсинга. При нескольких значениях результаты смешиваются и блок `Work type` на detail page не всегда присутствует — нельзя надёжно различить. Решение: несколько запросов с разными значениями `work_format`.

---

### Изменение 4: Обновить `scrape_jobs()` в `jobspy/__init__.py`

```python
def scrape_jobs(
    ...
    work_format: str | None = None,           # "remote" | "hybrid" | "onsite"
    seniority_levels: list[str] | None = None,  # ["entry", "mid_senior", ...]
    ...
):
    # Парсинг work_format
    work_format_enum = WorkFormat(work_format.lower()) if work_format else None

    # Парсинг seniority_levels
    seniority_enum = None
    if seniority_levels:
        seniority_enum = [SeniorityLevel(sl.lower()) for sl in seniority_levels]

    scraper_input = ScraperInput(
        ...
        work_format=work_format_enum,
        seniority_levels=seniority_enum,
    )
```

---

## LinkedIn: стратегия определения work_format

### Проблема с парсингом detail page

Пользователь проверил реальные вакансии LinkedIn: блок `Work type` **присутствует не у всех вакансий**. Пример реальной структуры `description__job-criteria-list`:
- Seniority level ✓
- Employment type ✓
- Job function ✓
- Industries ✓
- **Work type — может отсутствовать**

### Решение: `f_WT` как первичный источник + keyword как fallback с флагом

Ключевое наблюдение: если запрос отправлен с `f_WT=3` (Remote), LinkedIn **гарантированно** возвращает только Remote-вакансии. Это надёжнее любого парсинга.

**Стратегия определения `work_format` для каждой вакансии**:

```
1. Если фильтр work_format был передан в запросе (одно значение)
   → все вакансии гарантированно имеют этот формат
   → проставляем его каждой вакансии без дополнительных запросов

2. Если linkedin_fetch_description=True (и фильтр не передан)
   → пробуем распарсить h3[Work type] с detail page
   → если найдено — это точное значение

3. Fallback (если не нашли структурно)
   → keyword detection в title/description/location
   → управляется флагом linkedin_use_keyword_work_format_fallback (default=True)
   → если False — work_format остаётся None когда не определён структурно
```

### Новый параметр `ScraperInput`

```python
class ScraperInput(BaseModel):
    ...
    linkedin_use_keyword_work_format_fallback: bool = True
```

В `scrape_jobs()` пробрасывается:
```python
def scrape_jobs(
    ...
    linkedin_use_keyword_work_format_fallback: bool = True,
):
```

---

## Изменения в `jobspy/linkedin/util.py`

### Маппинги (добавить в начало файла)

```python
from jobspy.model import WorkFormat, SeniorityLevel

LINKEDIN_SENIORITY_CODE = {
    SeniorityLevel.INTERNSHIP: 1,
    SeniorityLevel.ENTRY: 2,
    SeniorityLevel.ASSOCIATE: 3,
    SeniorityLevel.MID_SENIOR: 4,
    SeniorityLevel.DIRECTOR: 5,
    SeniorityLevel.EXECUTIVE: 6,
}

LINKEDIN_WORK_FORMAT_CODE = {
    WorkFormat.ONSITE: 1,
    WorkFormat.REMOTE: 2,
    WorkFormat.HYBRID: 3,
}

LINKEDIN_WORK_FORMAT_FROM_TEXT = {
    "remote": WorkFormat.REMOTE,
    "hybrid": WorkFormat.HYBRID,
    "on-site": WorkFormat.ONSITE,
    "onsite": WorkFormat.ONSITE,
    "in person": WorkFormat.ONSITE,
}
```

### Новая функция `parse_work_format_from_page()`

```python
def parse_work_format_from_page(soup: BeautifulSoup) -> WorkFormat | None:
    """
    Tries to extract work format from LinkedIn job detail page criteria block.
    Returns None if 'Work type' block is absent (common — not all jobs have it).
    """
    h3_tag = soup.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: text and "Work type" in text.strip(),
    )
    if not h3_tag:
        return None

    span = h3_tag.find_next_sibling(
        "span",
        class_="description__job-criteria-text description__job-criteria-text--criteria",
    )
    if not span:
        return None

    raw = span.get_text(strip=True).lower()
    return LINKEDIN_WORK_FORMAT_FROM_TEXT.get(raw)
```

### Обновлённая `is_job_remote()` + новая `determine_work_format()`

```python
def determine_work_format(
    page_work_format: WorkFormat | None,
    filter_work_format: WorkFormat | None,
    title: str,
    description: str | None,
    location: Location,
    use_keyword_fallback: bool = True,
) -> WorkFormat | None:
    """
    Determines work format for a single job using a priority chain:
    1. Inferred from search filter (single value → guaranteed for all results)
    2. Parsed from detail page (structural, accurate but not always present)
    3. Keyword detection in title/description/location (fallback, least accurate)
    4. None (when use_keyword_fallback=False and no structural data found)
    """
    # Priority 1: filter value — most reliable (LinkedIn guarantees all results match)
    if filter_work_format is not None:
        return filter_work_format

    # Priority 2: structural from detail page (present only for some jobs)
    if page_work_format is not None:
        return page_work_format

    # Priority 3: keyword fallback
    if use_keyword_fallback:
        location_str = location.display_location() if location else ""
        full_string = f'{title} {description or ""} {location_str}'.lower()
        if any(kw in full_string for kw in ("remote", "work from home", "wfh")):
            return WorkFormat.REMOTE
        if "hybrid" in full_string:
            return WorkFormat.HYBRID

    return None


def is_job_remote(work_format: WorkFormat | None) -> bool:
    """Derives is_remote bool from work_format. Kept for backward compatibility."""
    return work_format == WorkFormat.REMOTE
```

---

## Изменения в `jobspy/linkedin/__init__.py`

### Исправить баг `f_WT` и добавить `f_E`

```python
# Было (БАГ):
"f_WT": 2 if scraper_input.is_remote else None,

# Стало:
f_wt = None
if scraper_input.work_format:
    f_wt = str(LINKEDIN_WORK_FORMAT_CODE[scraper_input.work_format])
elif scraper_input.is_remote:
    # обратная совместимость: is_remote=True → Remote (2)
    f_wt = "2"

f_e = None
if scraper_input.seniority_levels:
    codes = [str(LINKEDIN_SENIORITY_CODE[sl]) for sl in scraper_input.seniority_levels
             if sl in LINKEDIN_SENIORITY_CODE]
    f_e = ",".join(codes) if codes else None

params = {
    ...
    "f_WT": f_wt,
    "f_E": f_e,
    ...
}
```

### Использование в `_get_job_details()`

```python
def _get_job_details(self, job_id: str) -> dict:
    ...
    return {
        "description": description,
        "job_level": parse_job_level(soup),
        "company_industry": parse_company_industry(soup),
        "job_type": parse_job_type(soup),
        "work_format_from_page": parse_work_format_from_page(soup),  # ← новое
        "job_url_direct": self._parse_job_url_direct(soup),
        "company_logo": company_logo,
        "job_function": job_function,
    }
```

### Использование в `_process_job()`

```python
def _process_job(self, job_card, job_id, full_descr):
    ...
    job_details = {}
    if full_descr:
        job_details = self._get_job_details(job_id)
        description = job_details.get("description")

    work_format = determine_work_format(
        page_work_format=job_details.get("work_format_from_page"),
        filter_work_format=self.scraper_input.work_format,
        title=title,
        description=description,
        location=location,
        use_keyword_fallback=self.scraper_input.linkedin_use_keyword_work_format_fallback,
    )

    return JobPost(
        ...
        is_remote=is_job_remote(work_format),
        work_format=work_format,
        ...
    )
```

---

## Изменения в `jobspy/util.py`

```python
desired_order = [
    ...
    "is_remote",
    "work_format",   # добавить после is_remote
    "job_level",
    ...
]
```

---

## Изменения в `jobspy/__init__.py` — DataFrame pipeline

```python
# В цикле обработки JobPost:
job_data["work_format"] = (
    job_data["work_format"].value
    if isinstance(job_data.get("work_format"), WorkFormat)
    else job_data.get("work_format")  # уже строка или None
)

# Автоматически синхронизировать is_remote с work_format
if job_data.get("work_format") is not None:
    job_data["is_remote"] = (job_data["work_format"] == WorkFormat.REMOTE.value)
```

---

## Итоговый список файлов для изменения

| Файл | Что меняем |
|---|---|
| `jobspy/model.py` | Добавить `WorkFormat`, `SeniorityLevel` enum; `work_format` в `JobPost`; `work_format`, `seniority_levels`, `linkedin_use_keyword_work_format_fallback` в `ScraperInput` |
| `jobspy/__init__.py` | Параметры `work_format`, `seniority_levels`, `linkedin_use_keyword_work_format_fallback` в `scrape_jobs()`; `work_format` enum→string и синхронизация `is_remote` в pipeline |
| `jobspy/linkedin/__init__.py` | Исправить `f_WT` баг; добавить `f_E`; вызвать `determine_work_format()`; передать `work_format` в `JobPost` |
| `jobspy/linkedin/util.py` | Добавить `LINKEDIN_SENIORITY_CODE`, `LINKEDIN_WORK_FORMAT_CODE`, `LINKEDIN_WORK_FORMAT_FROM_TEXT`; добавить `parse_work_format_from_page()`; добавить `determine_work_format()`; упростить `is_job_remote()` |
| `jobspy/util.py` | Добавить `"work_format"` в `desired_order` |

---

## Roadmap для других источников (не в этой итерации)

Таблица как маппить будущие источники на `WorkFormat` и `SeniorityLevel`:

### WorkFormat

| Источник | Их данные | Маппинг на WorkFormat |
|---|---|---|
| Indeed | `job.attributes[].label` ∈ {"Remote", "Hybrid"} | `"remote"→REMOTE`, `"hybrid"→HYBRID`, иначе `ONSITE` |
| Glassdoor | `locationType == "S"` | `"S"→REMOTE`, иначе нет данных (`None`) |
| ZipRecruiter | Нет структурных данных | `None` (пока keyword fallback) |
| Google | Нет структурных данных | `None` (пока keyword fallback) |

### SeniorityLevel

| Источник | Их данные | Маппинг на SeniorityLevel |
|---|---|---|
| LinkedIn | `h3[Seniority level]` span text | `"entry level"→ENTRY`, `"mid-senior level"→MID_SENIOR` и т.д. |
| Indeed | Нет в API | Нет |
| Glassdoor | Нет | Нет |
| ZipRecruiter | Нет | Нет |
| Google | Нет структурных данных | Нет |

---

## Пример использования после реализации

```python
from jobspy import scrape_jobs

# Только remote вакансии — надёжно через f_WT=3
# work_format проставляется всем вакансиям автоматически из фильтра
jobs = scrape_jobs(
    site_name="linkedin",
    search_term="Python Developer",
    work_format="remote",
)
# jobs["work_format"] → "remote" для всех строк
# jobs["is_remote"]   → True для всех строк

# Hybrid вакансии отдельным запросом
jobs_hybrid = scrape_jobs(
    site_name="linkedin",
    search_term="Python Developer",
    work_format="hybrid",
)
# jobs_hybrid["work_format"] → "hybrid" для всех строк

# Если нужно и remote, и hybrid — два запроса + concat:
import pandas as pd
jobs_all = pd.concat([jobs, jobs_hybrid], ignore_index=True)

# Фильтр по seniority (список — ОК, т.к. каждая вакансия имеет свой уровень на detail page)
jobs = scrape_jobs(
    site_name="linkedin",
    search_term="Product Manager",
    seniority_levels=["mid_senior", "director"],
    work_format="remote",
)

# Без фильтра work_format, с парсингом с detail page
jobs = scrape_jobs(
    site_name="linkedin",
    search_term="Data Scientist",
    linkedin_fetch_description=True,  # включает parse_work_format_from_page()
)
# jobs["work_format"] → "remote"/"hybrid"/"onsite"/None (из detail page если блок есть, иначе keyword)

# Отключить keyword fallback — work_format=None когда нет ни фильтра, ни структурных данных
jobs = scrape_jobs(
    site_name="linkedin",
    search_term="DevOps Engineer",
    linkedin_use_keyword_work_format_fallback=False,
)
```
