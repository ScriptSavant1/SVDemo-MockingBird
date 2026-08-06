# AI-Assisted Development Playbook (generic — reuse across projects)

This is not project-specific. Copy this file into any new or existing
project's root and it applies as-is. Works with any coding agent (Claude
Code, Kiro, etc.) — nothing here assumes a specific tool.

---

## Part 1 — Before you write a single line of code

**Define scope in writing, even for a small project.** One paragraph: what the
project does, who uses it, what it explicitly does NOT do. AI agents drift when
scope is only in your head.

**Decide your knowledge structure before coding starts, not after.**

`/ai-brain/` holds AI-facing knowledge — the docs an agent needs to work
safely, kept close to the code:

```
/ai-brain/
  ARCHITECTURE.md     - module map, data flow (fill in as it emerges — doesn't
                        need to be complete on day 1, but start the file)
  CONVENTIONS.md       - naming, style, error handling — pick these up front,
                        agents drift more without stated conventions
  AI_RULES.md          - non-negotiables (see Part 3 below)
  FEATURES.md          - one entry per feature as you build it
  CHANGELOG.md         - append-only
  BUGS.md              - known bugs, root cause, fix status
  DECISIONS.md         - short ADR-style log: why a significant technical
                        choice was made
  CONFIGURATION.md     - every config value/env var, default, required or not
  GLOSSARY.md          - domain terms, protocol names, internal jargon
  vendor/              - if this project depends on external/vendor APIs,
                        one subfolder per vendor/version (see
                        documentation-automation-system.md for the full
                        picture, including which docs stay at project root
                        instead of here)

/regression-tests/
  README.md            - how tests are run and checked
  <feature-or-module>/
    inputs/
    expected-outputs/

/unit-tests/            - per testing-strategy-and-definition-of-done.md
  README.md            - how unit tests are organized/run for this stack
```

Project-root-level docs (README.md, DEPLOYMENT.md, TESTING.md,
CONTRIBUTING.md, RELEASE_NOTES.md, BUSINESS_CONTEXT.md, SECURITY.md) are
covered in `documentation-automation-system.md` Part 1 — they're
external/human-facing rather than AI-working-knowledge, so they live at the
project root, not inside `/ai-brain/`. Not every doc needs to exist on day
one; create them as they become relevant.

**Set up regression tests before the first feature is "done," not after three
features exist.** Retrofitting tests onto untested code is much harder than
building the habit from feature #1.

**Write AI_RULES.md before the first prompt to any agent.** See Part 3 — this
is the single highest-leverage file for keeping an agent from deviating.

---

## Part 2 — Every time you ask an agent to do something

Scale the process to the size of the change. Don't apply heavyweight process to
a one-line fix, and don't skip process on anything that touches shared code.

**Trivial, isolated change** (typo, copy tweak, single-function bugfix with no
callers elsewhere):
- Just ask for it. Have the agent name the file(s) touched in its reply.

**Anything that touches a module other code depends on, or adds a new
feature:**
1. Ask the agent for an **impact analysis first, as text, not code**: affected
   files, affected features/modules, risk level, backward-compatibility notes.
2. Review that analysis yourself before saying "go."
3. Only then let it implement.
4. After implementation, it runs unit tests and regression tests for every
   affected area *before* declaring the task complete.
5. It updates docs per the documentation-automation-system.md matrix and
   updates CHANGELOG.md and FEATURES.md in the same session — don't let docs
   drift a session behind the code.

**Never let an agent silently:**
- Update `expected-outputs/` in regression tests to make a failing test pass.
  Only you approve intentional behavior changes.
- Skip a failing test and move on to something else without flagging it.
- Guess at third-party/vendor API behavior it isn't sure of — it should say
  "not confirmed" rather than assume.
- Commit secrets, credentials, tokens, or keys — see the secrets rule in
  testing-strategy-and-definition-of-done.md Part 1B.

---

## Part 3 — AI_RULES.md starter (copy and adapt)

```
- Never remove or change existing functionality without saying so explicitly
  and naming what's affected.
- Before editing any file, list what else depends on it.
- Do a written impact analysis before implementing anything beyond a trivial,
  isolated fix — wait for confirmation before writing code.
- Never guess external/vendor API behavior — check documented references; if
  none exist, say so instead of assuming.
- After any change: write/update unit tests, run relevant regression tests,
  and stop + report if any fail rather than continuing.
- Update documentation per the documentation-automation-system.md matrix, and
  update CHANGELOG.md/FEATURES.md as part of the same task, not later.
- When uncertain about intent, ask rather than assume.
- Prefer small, reviewable diffs over full-file rewrites when editing existing
  files.
- Apply the Definition of Done checklist from
  testing-strategy-and-definition-of-done.md before marking any non-trivial
  task complete, including its code-level guardrails (fail loudly, scrutinize
  inverted conditions, never commit secrets, flag sensitive data handling).
- Run (or schedule) the periodic architecture-doc audit from
  documentation-automation-system.md on the cadence stated in that file.
```

---

## Part 4 — When requirements or dependencies change later

(e.g. a vendor updates their API/docs, or you change project requirements)

1. Don't ask the agent to "just implement the change." Ask it first to compare
   old vs. new behavior and produce a change summary: what's new, what's
   deprecated, what breaks existing usage.
2. Ask which existing features/modules are affected, referencing FEATURES.md.
3. Get an implementation plan before code, same as Part 2.
4. After implementing, test not just the changed area but anything the impact
   analysis flagged as dependent on it.
5. Update the relevant reference doc (vendor doc snapshot, ARCHITECTURE.md,
   whichever changed) in the same session.

---

## Part 5 — Generic kickoff prompt template

Fill in the brackets and paste as your first message to any agent on a new
project (or use `project-setup-prompt.md` for an existing one):

```
You are acting as Senior Software Architect for [PROJECT NAME], which
[ONE-PARAGRAPH DESCRIPTION OF WHAT IT DOES].

This project will evolve over time and I may work on it with more than one
AI coding tool, so treat all project knowledge as tool-agnostic — don't
assume anything specific to you.

Before any implementation: read AI_RULES.md, ARCHITECTURE.md, and
CONVENTIONS.md in /ai-brain/ if they exist; if they don't yet, propose a
first version based on [WHAT EXISTS SO FAR / "this is a fresh project"]
and show it to me before creating files.

Also read documentation-automation-system.md and
testing-strategy-and-definition-of-done.md in this project's root, and
follow them for every task, including the code-level guardrails and the
periodic doc-audit cadence stated in those files.

For every task going forward: scale process to the size of the change. For
anything beyond a trivial fix, give me a written impact analysis before
writing code, and wait for my go-ahead. Write unit tests for new/changed
functions, run regression tests, and apply the Definition of Done checklist
before declaring any non-trivial task complete.

Do not implement everything in one pass. Confirm scope with me at each
meaningful step rather than assuming.
```

---

## Notes for yourself

- This playbook is a strong nudge to the agent, not a guarantee — it will
  reduce deviation and missed regressions significantly, but the actual safety
  net is the tests, not the rules file. Keep test coverage growing as the
  project grows.
- Revisit AI_RULES.md every so often — if you notice a recurring failure
  pattern, add a specific rule for it rather than hoping the agent infers it.
