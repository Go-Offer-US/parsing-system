# Подключение форка JobSpy в основной проект

## Контекст

Официальная библиотека `python-jobspy` установлена из PyPI. Этот репозиторий — форк с кастомными изменениями. Чтобы основной проект использовал форк вместо официальной версии, нужно заменить PyPI-зависимость на локальную.

---

## Способ 1: Git URL везде — рекомендуется

Единственный способ который работает одинаково и локально, и на Render. Локальный путь в `pyproject.toml` **нельзя коммитить** — Render не знает про папки на твоей машине и деплой упадёт.

### Шаг 1 — Убрать официальную версию

В директории основного проекта:

```bash
poetry remove python-jobspy
```

### Шаг 2 — Добавить форк из Git

```bash
poetry add git+https://github.com/Go-Offer-US/parsing-system.git#develop
```

### Шаг 3 — Применить изменения

```bash
poetry install
```

Локальный цикл разработки:
```
правишь JobSpy → git push в parsing-system → poetry update python-jobspy → тестируешь
```

---

## Способ 2: Editable локально без изменения pyproject.toml

Если правишь библиотеку очень активно и push каждый раз неудобен — можно поставить editable-версию напрямую в venv, не трогая `pyproject.toml`. Тогда файл всегда содержит Git URL и безопасен для деплоя.

```bash
# Найти путь к venv основного проекта
poetry env info --path

# Установить editable поверх Git-версии (только в локальный venv, pyproject.toml не меняется)
<путь-из-команды-выше>/bin/pip install -e /Users/miroslavpeskov/Desktop/EasyWork/JobSpy
```

Изменения в JobSpy сразу видны без push и переустановки. После `poetry install` или `poetry update` editable слетит — нужно повторить `pip install -e`.

> **Важно**: `pyproject.toml` при этом способе остаётся с Git URL. Локальный путь никуда не записывается — деплой на Render работает штатно.

---

## Способ 3: Зависимость через Git (детали)

Подходит когда форк залит в приватный или публичный GitHub-репозиторий и нужно чтобы другие разработчики или сервер могли поставить его без доступа к локальной папке.

### Шаг 1 — Убрать официальную версию

```bash
poetry remove python-jobspy
```

### Шаг 2 — Добавить зависимость из Git

JobSpy хранится в репозитории `Go-Offer-US/parsing-system`. Команды для разных сценариев:

```bash
# Ветка develop (основная рабочая ветка)
poetry add git+https://github.com/Go-Offer-US/parsing-system.git#develop

# Ветка main (стабильный релиз)
poetry add git+https://github.com/Go-Offer-US/parsing-system.git#main

# Конкретный коммит — самый надёжный вариант для продакшена
poetry add git+https://github.com/Go-Offer-US/parsing-system.git#abc1234
```

В `pyproject.toml` появится:

```toml
[tool.poetry.dependencies]
python-jobspy = {git = "https://github.com/Go-Offer-US/parsing-system.git", branch = "develop"}
```

> **Работает и локально, и на сервере** — Poetry тянет код напрямую из GitHub по HTTPS. Никакой локальной папки не нужно. Единственное условие — репозиторий должен быть доступен (публичный или есть токен/SSH-доступ).

### Шаг 3 — Применить изменения

```bash
poetry install
```

---

## Как вернуться на официальную версию

```bash
poetry remove python-jobspy
poetry add python-jobspy
```

---

## Проверка что работает нужная версия

```bash
poetry run python -c "import jobspy; print(jobspy.__file__)"
```

Путь должен указывать на твой форк, а не на папку в кеше Poetry.

---

## Частые проблемы

**`poetry add` падает с ошибкой про уже существующую зависимость**
→ Сначала выполни `poetry remove python-jobspy`, потом добавляй форк.

**Изменения в форке не применяются в основном проекте**
→ При локальном пути с `--editable` изменения применяются автоматически. При Git-зависимости нужно обновить явно:
```bash
poetry update python-jobspy
```

**На сервере нет доступа к локальной папке**
→ Используй Способ 2 (Git-зависимость).
