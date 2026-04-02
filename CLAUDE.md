## AI Development Workflow

### Planning — required for complex tasks

Before writing any code for a complex or unclear task — stop and plan first.

**When to plan:** the task touches multiple files, involves architectural decisions, or has unclear requirements.

**How to plan:**

1. Ask clarifying questions **in Russian** until the task, expected result, and edge cases are fully clear. Do not start
   coding while anything is ambiguous.
2. Write a structured plan and save it to `.claude/plans/<task-name>.md`
3. Present the plan to the developer and get explicit approval before proceeding
4. Only start coding after the plan is agreed upon

**Plan file must include:**

- Goal and expected result
- What files will be changed and why
- Step-by-step implementation breakdown
- Open questions and risks

### Self-review — required after every implementation

After writing code — always do a review pass before considering the task done:

1. **Logic and bugs** — re-read the implementation and look for logical errors, edge cases, and potential failures
2. **Compliance with plan** — verify the implementation matches what was planned and agreed. If it drifted, explain why.
3. **Simplicity check** — ask: "Can this be done simpler without losing clarity?" If yes — simplify. Complexity is only
   justified when the problem genuinely demands it.

### Documentation — required after implementation

After completing a feature — always document the work:

1. Check `docs/projects/` for an existing file related to the feature
2. Update the existing file if it exists, or create a new folder/file for a new feature
3. If unsure where to write — ask the developer before creating new files
4. Follow documentation guidelines in `docs/dev/create_doc.md`

---

## Skills

Available Claude Code skills in `.claude/skills/`:

| Skill        | Trigger                                             | What it does                                                                                                                  |
|--------------|-----------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `onboarding` | "онбординг", "расскажи про проект", "с чего начать" | Interactive onboarding walkthrough for new developers — covers architecture, environment, key services, patterns, and testing |

---

## Python Coding Standards

### Core principles

**KISS — Keep It Simple:** Simplicity and readability are the highest priority. If a simple solution exists, use it.
Avoid clever constructs that require explanation.

**SOLID — especially SRP:** Every function, class, and module should have one reason to change. Split responsibilities
early — it's cheaper than refactoring later.

**DRY — Don't Repeat Yourself:** Extract repeated logic into functions or classes. But don't abstract prematurely — wait
until you see the pattern at least twice.

**No overengineering:** Do not create abstractions "for the future." Solve the current problem in the most direct way
possible. Three similar lines of code are better than a premature abstraction.

### Specific rules

**Functions and classes**

- Keep functions small and focused — one function, one responsibility
- Prefer flat over nested: if you're indenting more than 3 levels, extract a function
- Name functions as verbs (`get_active_sessions`, `process_message`), classes as nouns (`SessionRepository`,
  `MessageHandler`)
- Avoid functions longer than ~40-80 lines — if it's longer, split it

**Comments and documentation**

- All comments and docstrings must be in English
- Comment *why*, not *what* — the code explains what it does, comments explain why a decision was made
- Avoid obvious comments: `# increment counter` above `count += 1` adds no value

**Imports and structure**

- Group imports: stdlib → third-party → local (`shared/`, `services/`, etc.)
- isort is enforced by ruff automatically
- Do not use wildcard imports (`from module import *`)

**Error handling**

- Be specific with exceptions — catch `ValueError`, not bare `Exception`, unless you have a reason
- Always log errors with context: `logger.error(f"Failed to process session {session_id}: {e}")`
- Do not silence exceptions with empty `except` blocks

**Type hints**

- Use type hints on all function signatures
- Use `Optional[X]` or `X | None` for nullable values (Python 3.10+ style preferred)
- Use Pydantic schemas for data validation at system boundaries (API input, external data)

**Database access**

- Never write raw SQL — always use repositories from `shared/repositories/`
- Never bypass the repository layer with direct ORM queries in services or cron jobs
- Use `async/await` consistently — this is an async codebase

**Consistency**

- Before writing new code, read the surrounding file and follow existing patterns
- Do not "improve" code style in files you're not changing — keep PRs focused
- Follow PEP 8 — ruff enforces it automatically