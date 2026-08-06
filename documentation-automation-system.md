# Documentation Automation System (generic — reuse across projects)

Pairs with `ai-assisted-development-playbook.md`. That file governs *how* an
agent implements changes safely; this one governs *which documents* get
touched, *when*, *where they live*, and *who owns the final call* on each.
Copy into any project's root (new or existing) and let the agent read it
before starting work.

The core idea: not every doc updates on every change. Doc updates are tied to
the *type* of change, not fired blindly on every task. This keeps docs
accurate instead of bloated, and keeps you from burning tokens rewriting a
deployment guide because you renamed a variable.

---

## Part 1 — The full document set, what each is for, and where it lives

| Document | Purpose | Location | Owner |
|---|---|---|---|
| `ARCHITECTURE.md` | Module map, data flow, how pieces fit together | `/ai-brain/` | AI maintains |
| `CONVENTIONS.md` | Coding standards, naming, patterns to follow | `/ai-brain/` | You set once, AI follows |
| `AI_RULES.md` | Non-negotiable working rules for any agent | `/ai-brain/` | You approve, AI follows |
| `FEATURES.md` | Feature registry — one entry per feature, status, owner module, tests | `/ai-brain/` | AI maintains |
| `CHANGELOG.md` | Append-only technical log: what changed, when | `/ai-brain/` | AI maintains, append-only |
| `BUGS.md` (or `ISSUES.md`) | Known bugs, history, root cause, fix status | `/ai-brain/` | AI maintains |
| `DECISIONS.md` (ADR log) | Short record of *why* a significant technical choice was made | `/ai-brain/` | AI drafts at decision time, you approve |
| `CONFIGURATION.md` | Every config value/env var, what it does, default, required vs optional | `/ai-brain/` | AI maintains |
| `GLOSSARY.md` | Domain terms (protocol names, vendor-specific jargon, internal terminology) | `/ai-brain/` | AI maintains |
| `vendor/<name>/*.md` | Vendor/third-party API references, one file per vendor or version | `/ai-brain/vendor/` | AI maintains, flags unconfirmed behavior |
| `README.md` | First-contact overview: what it is, quick setup, quick usage | project root | AI drafts, you approve |
| `RELEASE_NOTES.md` | User/business-facing summary per version — "what's new," not implementation detail | project root | AI drafts, you approve before publishing |
| `DEPLOYMENT.md` | How to build, deploy, roll back; environments; required config | project root | AI drafts, **you verify before trusting it** — wrong deployment docs are dangerous |
| `TESTING.md` | Test strategy, how to run regression/unit tests, how to add new test cases | project root | AI maintains |
| `CONTRIBUTING.md` | For future-you or anyone else touching the repo: setup, PR process, standards | project root | AI drafts, you approve |
| `BUSINESS_CONTEXT.md` | Why this exists, who uses it, what problem it solves, non-goals | project root | **You own this — AI should not invent business rationale** |
| `SECURITY.md` | How secrets/credentials are handled, anything explicitly NOT to hardcode or log | project root | You review carefully; AI flags concerns but you decide policy |

Rule of thumb for the split: `/ai-brain/` is the working knowledge an agent
needs open while coding — architecture, rules, bugs, decisions, config,
vendor references. Project root holds docs aimed at humans (including
future-you) or external audiences — setup instructions, deployment,
contribution process, business rationale, security policy.

Not every project needs every file on day one. Create them as they become
relevant — an empty `DEPLOYMENT.md` before you've deployed anything is just
noise. But when the relevant milestone hits (first deploy, first real
decision, first external contributor), the agent should be the one to notice
and say "this doc should exist now," not wait for you to ask.

---

## Part 2 — What triggers what (the update matrix)

This is the part that makes automation *safe* instead of noisy.

| Change type | Docs to update in the same session |
|---|---|
| Trivial fix (typo, isolated one-line bug) | `CHANGELOG.md` only |
| Bug fix (non-trivial) | `CHANGELOG.md`, `BUGS.md` |
| New feature | `CHANGELOG.md`, `FEATURES.md`, `ARCHITECTURE.md` (if it adds a module/data flow), `README.md` (if it changes usage) |
| Changed/removed existing behavior | `CHANGELOG.md`, `FEATURES.md`, `ARCHITECTURE.md`, and flag in `RELEASE_NOTES.md` as a breaking change |
| New config/env var | `CONFIGURATION.md` |
| Significant architectural or technical decision (e.g. "why SQLite vs. markdown," "why this library") | `DECISIONS.md` |
| First deployment / deployment process changes | `DEPLOYMENT.md` |
| Vendor/third-party API change absorbed into the project | `CHANGELOG.md`, `FEATURES.md`, plus the relevant file under `/ai-brain/vendor/` |
| New domain term introduced | `GLOSSARY.md` |
| Release cut (you're about to ship/tag a version) | `RELEASE_NOTES.md` (human-readable), review `README.md` for staleness |

**Rule for the agent: before finishing any task, check this table, identify
which row applies, update exactly those docs — not more, not fewer.** If a
change doesn't clearly match a row, it should ask you rather than guess.

### Rule: periodic architecture-doc audit is mandatory, not optional

Per-task updates catch drift caused by *changes*. They don't catch drift that
was already there — an architecture doc can be wrong about code nobody has
touched in months, and the per-task matrix above will never flag it because
no task ever triggers on it. This was found twice in real use on the same
project (a stale entry-point/file-load-order section, and two "NEVER BREAK"
reference tables missing several real, load-bearing behaviors) — neither was
caused by a recent change; both had just quietly drifted.

**Default cadence: monthly, or before every release, whichever comes
first.** Override this in your own copy of this file if a project needs a
different cadence — but pick a number; don't leave it unset.

**Also run this audit — not just on the calendar — whenever one of these
happens, since each is a moment drift is especially likely:**
- Before every release
- After a major refactor
- After any architecture-level change (new module boundary, changed data
  flow, changed entry point)
- After a dependency or vendor version upgrade
- After a security review

```
- On the stated cadence, run a dedicated audit: read-only, agent re-reads
  the actual code behind each architecture/reference doc's claims and
  reports every mismatch, however small. This is a distinct task, not
  folded into a feature request.
- Any table documenting "always true" invariants, types, or behaviors (e.g.
  a sentinel table, an extractor type table, a status enum) is a first
  priority in this audit — these are exactly the tables that silently
  become incomplete as new cases get added to the code without a matching
  doc update.
- The output of this audit is a plain list of mismatches, same format as
  project-audit-prompt.md — confirmed vs. inferred, doc says X, code does Y.
  Fix docs in a dedicated pass, not folded into an unrelated code task.
```

---

## Part 3 — Ownership: what AI drafts vs. what you must personally approve

Three tiers, and the agent should know which tier it's operating in:

1. **AI maintains freely** — CHANGELOG.md, BUGS.md, FEATURES.md,
   CONFIGURATION.md, GLOSSARY.md, TESTING.md, ARCHITECTURE.md,
   `vendor/*.md`. These are derived from what the code actually does — low
   risk if imperfect, easy to correct.
2. **AI drafts, you approve before it's treated as final** — README.md,
   CONTRIBUTING.md, RELEASE_NOTES.md, DECISIONS.md. These represent judgment
   calls or external-facing communication — worth a human pass.
3. **You own, AI never invents** — BUSINESS_CONTEXT.md, and the *policy*
   content of SECURITY.md. Why the project exists, who it serves, what
   tradeoffs were accepted for business reasons — an AI inferring this from
   code will get it wrong or make it up. If this doc doesn't exist yet, the
   agent should ask you to write it, not draft one from guesses.

---

## Part 4 — Rules to append to AI_RULES.md

```
- After finishing any task, consult the documentation update matrix and
  update exactly the docs that match the change type — not a blanket
  "update everything" pass.
- Never draft BUSINESS_CONTEXT.md or SECURITY.md policy content from
  inference — ask instead.
- Treat README.md, RELEASE_NOTES.md, CONTRIBUTING.md, and DECISIONS.md as
  drafts requiring my approval, not final on save.
- When a milestone is reached that implies a new doc should exist
  (first deployment, first real architectural decision, first external
  contributor) — say so explicitly rather than silently skipping it or
  silently creating it unasked.
- CHANGELOG.md entries are append-only — never rewritten or summarized away.
- If a change doesn't clearly match a row in the update matrix, ask which
  docs should be touched rather than guessing.
- Run the periodic architecture-doc audit on the cadence stated above —
  don't wait to be asked.
```

---

## Part 5 — Add to the generic kickoff prompt (Part 5 of the playbook)

Append this paragraph to that template:

```
Also read documentation-automation-system.md in the project root. After every
task, consult its update matrix and update only the documents that match the
type of change made — do not blanket-update all documentation on every task.
Treat README.md, RELEASE_NOTES.md, CONTRIBUTING.md, and DECISIONS.md as
drafts I need to approve, not final. Never invent content for
BUSINESS_CONTEXT.md or SECURITY.md policy — ask me instead. Run the periodic
architecture-doc audit on the cadence stated in that file.
```

---

## What you were still missing (worth knowing, not necessarily building today)

- **Architecture Decision Records (ADRs)** — the `DECISIONS.md` row above is
  a lightweight version of this. Industry-standard practice for capturing
  *why*, not just *what* — genuinely useful on a long-lived project, cheap to
  maintain, and the thing people miss most until they need it ("why did we
  choose X over Y two years ago?").
- **Versioning your docs alongside your releases**, if this project will ever
  ship distinct versions people rely on — otherwise "the docs" describe
  whatever's on main, which confuses anyone on an older version.
- **A basic CONTRIBUTING.md even if you're the only contributor right now** —
  future-you, six months from now, is effectively a new contributor.
- **Not automating what shouldn't be automated**: business rationale and
  security policy are the two things worth deliberately keeping human-owned,
  covered in Part 3 above.

Nothing here is exotic — it's the same discipline real teams use, scaled down
to a solo/two-tool setup. The main things to hold onto are Part 2's matrix
(what updates when) and Part 1's location split (what lives in /ai-brain/
vs. project root) — together they keep "everything updates automatically"
from becoming "everything updates sloppily, in the wrong place."

---

## Part 6 — Keeping the docs themselves from growing unbounded

Append-only files (CHANGELOG.md especially) and running logs (BUGS.md,
session-state files) are correct to keep append-only during normal work —
but "never delete" isn't the same as "never archive." Left alone
indefinitely, these files eventually get large enough that reading them
costs real context, which works against the whole point of this system.

```
- When CHANGELOG.md exceeds roughly a year of entries or becomes unwieldy to
  read in full, move older entries to CHANGELOG-ARCHIVE.md (or split by
  year) rather than trimming them — history is still valuable, just not in
  the file read every session.
- BUGS.md entries marked FIXED can move to a BUGS-ARCHIVE.md after a stated
  period (e.g. two release cycles) once you're confident the fix held —
  keep them findable, just out of the actively-scanned file.
- Any session-state file (e.g. a "current status" doc read at the start of
  every session) should reflect current state only — historical status
  belongs in CHANGELOG.md, not accumulated in the state file itself.
- Archiving is a docs-only task the agent can propose when a file's size
  starts costing noticeable context, but the actual move should be a
  distinct, visible action — not folded silently into an unrelated task.
```
