# Mockingbird — Documentation Standards
## What Gets Documented, How, and When

**Version:** 1.0  
**Last Updated:** 2026-06-14

---

## Principle

**Documentation is generated from code where possible. Written by AI for the rest.**  
No developer writes documentation manually unless it cannot be automated.

---

## Documentation Layers

### Layer 1 — Auto-Generated from Code (Zero Effort)

These are produced automatically on every CI build.

| What | Tool | Output Location | Triggered By |
|------|------|----------------|--------------|
| REST API docs | FastAPI built-in OpenAPI | `/docs` (Swagger UI), `/redoc` (Redoc) | Every FastAPI startup |
| Java API docs | springdoc-openapi | `/v3/api-docs`, `/swagger-ui.html` | Every Spring Boot startup |
| Python package deps | pip-licenses | `docs/licenses/python.md` | CI pipeline step |
| Java package deps | license-maven-plugin | `docs/licenses/java.md` | Maven build |
| Database schema | pg_dump + pgdoc | `docs/schema/current.sql` + `schema.html` | Migration applied |
| Test coverage | pytest-cov + JaCoCo | `docs/coverage/` | CI test step |
| Architecture diagram | Structurizr / Mermaid in CLAUDE.md | Auto-rendered in portal | On merge to main |

### Layer 2 — AI-Updated per Sprint (Claude Maintains These)

At the end of every implementation sprint, I update these files automatically without being asked:

| File | What Changes | Update Trigger |
|------|-------------|---------------|
| `docs/IMPLEMENTATION_PLAN.md` | Mark sprints completed, update % progress | Each sprint finished |
| `CHANGELOG.md` | New section per sprint with features built | Each sprint finished |
| `CLAUDE.md` | Update tech stack details if anything changed | Architectural decisions made |
| `docs/DECISIONS_LOG.md` | Mark pending inputs as resolved, add new decisions | Decision made |
| `START_HERE.md` | Update current status and next steps | Phase boundaries |

### Layer 3 — Per-Service README (Written Once, Updated on Breaking Changes)

Every microservice has a `README.md` in its directory. Written during Phase 1, updated when setup steps change.

Required sections in every service README:
1. **What This Service Does** (2 sentences)
2. **How to Run Locally** (exact commands)
3. **Environment Variables** (table of all env vars, required/optional)
4. **API Endpoints** (link to Swagger UI)
5. **Key Dependencies** (why each exists)
6. **Common Errors and Fixes**

### Layer 4 — Architecture Decision Records (ADR)

When a significant architectural decision is made, create an ADR in `docs/adr/`.

Format: `docs/adr/ADR-001-postgresql-over-mssql.md`

ADR Template:
```markdown
# ADR-NNN: Title

**Status:** Accepted | Superseded by ADR-XXX  
**Date:** YYYY-MM-DD

## Context
What problem are we solving?

## Decision
What did we decide?

## Rationale
Why this option over alternatives?

## Consequences
What becomes easier? What becomes harder?
```

Existing decisions from DECISIONS_LOG.md will be converted to ADRs during Phase 2.

---

## CHANGELOG Format

`CHANGELOG.md` follows Keep a Changelog standard. I create a new section after each sprint:

```markdown
## [Phase 1 Sprint 2] — 2026-07-XX

### Added
- Input auto-detector (OpenAPI, Postman, raw HTTP, Mockingbird JSON)
- Validation engine with line-level error messages
- WireMock mapping generator for GET/POST/PUT/DELETE

### Changed
- Parser interface updated to support streaming large files

### Fixed
- (any bugs fixed during this sprint)
```

---

## Documentation That Does NOT Exist in This Project

| What | Why Not |
|------|---------|
| Inline code comments explaining WHAT the code does | Code is self-documenting via naming |
| Tutorial videos | Out of scope for v1 |
| User manual PDF | Portal has built-in contextual help tooltips |
| Confluence pages | Docs live in the repo — single source of truth |

---

## Portal In-App Documentation

Every page in the Mockingbird portal has:
- **Page title** with one-line description
- **? Help tooltip** on every form field (what it is, what to enter)
- **Contextual error messages** (not "Invalid input" — "URL must start with / e.g., /api/v1/customers")
- **Guided mode** for first-time users (step-by-step wizard)
- **Example values** pre-filled in all form fields

---

## What I (Claude) Do Automatically Without Being Asked

- After each sprint: update IMPLEMENTATION_PLAN.md, create CHANGELOG.md entry
- After each architectural decision: update DECISIONS_LOG.md
- After creating a new service: create its README.md
- After a breaking API change: flag it in the sprint notes and update affected docs
- If a pending input (C1/C2/C3) is provided: update DECISIONS_LOG.md and START_HERE.md immediately

**You never need to say "update the docs" — I do it.**
