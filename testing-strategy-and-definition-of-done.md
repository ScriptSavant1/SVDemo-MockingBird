# Testing Strategy & Definition of Done (generic — reuse across projects)

Pairs with the playbook and documentation-automation-system files. This one
covers the *test pyramid* (unit, integration, regression), a set of
code-level guardrails learned from real audits, and a single **Definition of
Done** checklist that ties everything together so nothing gets skipped.

---

## Part 1 — The three test layers

| Layer | What it checks | Example for this kind of project |
|---|---|---|
| **1. Unit tests** | One function/module in isolation, including edge cases | Does the correlation function handle an empty response body? A malformed JSON payload? A missing header? |
| **2. Integration tests** | Multiple pieces working together correctly | Does the parser's output feed correctly into the generator without losing fields? |
| **3. Regression tests** | Whole pipeline, known input → known-good output, catches "did I break something that used to work" | Sample collection in, expected script out — see `/regression-tests/` in the playbook |

Regression tests alone won't catch a bug in a code path nobody happened to
regression-test. Unit tests are what force explicit thinking about edge cases
*per function* — that's the "each and every scenario" coverage you actually
want.

### Rule to add to AI_RULES.md

```
- Every new function or modified function gets unit tests covering: the
  normal case, at least one empty/missing-input case, and at least one
  malformed/invalid-input case — not just the happy path.
- When a bug is fixed, add a unit test that reproduces the bug first, so it
  can't silently regress later — this test stays in the suite permanently.
- Integration tests are added when two or more modules are wired together
  for the first time, or when the way they connect changes.
- Regression tests (whole-pipeline, input-file based) remain the final gate
  before a task is marked done — but they do not replace unit tests.
- If a function is genuinely hard to unit test as written (tightly coupled,
  hidden dependencies), flag that as a design issue rather than skipping
  tests for it.
```

---

## Part 1B — Code-level guardrails (found the hard way, worth having from day one)

These came from real audits that found a live inverted-condition bug, several
silent-failure code paths, and open questions about sensitive data handling —
none of which any rule above would have caught. Worth having in any project
from the start, not just after finding them the hard way.

### Rule: fail loudly, not silently

```
- Any code path that encounters malformed, unexpected, or unresolved input
  must either throw, log an explicit warning/error, or return a clearly
  invalid sentinel value that a caller is forced to check — never silently
  produce output that looks valid but isn't.
- When reviewing or writing code that does string/template substitution,
  parsing, or conditional file/resource operations: explicitly check what
  happens on the failure path, not just the success path. "What does this
  do when the expected thing ISN'T there?" is asked for every such function.
- If a legacy function already fails silently and fixing it is out of scope
  for the current task, flag it explicitly in the impact analysis or as a
  new BUGS.md entry rather than leaving it unmentioned.
```

### Rule: legacy high-risk code gets retrofitted tests, not just new code

```
- Untested code that's flagged as high-risk (wide blast radius, many
  dependents) does not stay untested just because nothing is currently
  changing it. When a project audit or impact analysis identifies such a
  file, schedule unit tests for its highest-risk functions as their own
  task — don't wait for an unrelated change to "justify" testing it.
- Prioritize by blast radius, not by recency: a widely-depended-on function
  with zero tests is a higher priority than full coverage on a small,
  isolated new feature.
```

### Rule: scrutinize inverted/negated conditions specifically

```
- When reviewing any conditional that gates a file, network, or resource
  operation (existence checks, permission checks, feature flags), explicitly
  state in plain language what the condition means and confirm it matches
  the intended behavior — inverted-logic bugs (a stray `!` or wrong
  comparison) are common, mechanical, and easy to miss on a normal read.
- This check applies especially to conditions guarding copy/write/delete
  operations, since the failure mode is often silent or misleading.
```

### Rule: never commit secrets or credentials

```
- Never hardcode API keys, tokens, passwords, connection strings, or
  certificates in source, tests, or fixture files. Use environment
  variables or a secrets manager, documented in CONFIGURATION.md (never the
  actual values).
- Before finalizing any change, scan the diff for anything that looks like a
  credential (long random strings, "key=", "password=", "token=", private
  key headers) and flag it rather than committing silently.
- If a credential is found already committed in the codebase (not introduced
  by the current task), stop and flag it explicitly — this needs rotation,
  not just removal, and is a decision for the human, not something to fix
  silently in passing.
```

### Rule: flag sensitive or personal data handling, don't decide policy

```
- If a task involves collecting, logging, storing, or transmitting personal
  or sensitive user/customer data (device fingerprints, IP addresses, names,
  credentials, health/financial data, etc.), flag this explicitly rather
  than treating it as a routine implementation detail.
- Do not decide on your own whether such collection is acceptable, needs
  disclosure, or needs a retention policy — that's a policy call for the
  human, same tier as SECURITY.md and BUSINESS_CONTEXT.md in
  documentation-automation-system.md.
- This applies even to internal/enterprise tools — "no external users" does
  not mean data handling questions don't apply.
```

---

## Part 2 — Definition of Done (the actual gate, per task)

This is the single checklist that pulls together everything across all
files. Have the agent run through this explicitly before calling any
non-trivial task complete:

```
DEFINITION OF DONE — check before marking any task complete:

[ ] Impact analysis was done and approved (for anything beyond a trivial fix)
[ ] Code change is scoped to what was approved — nothing extra touched
[ ] Unit tests written/updated for new or changed functions (happy path +
    empty/missing + malformed input)
[ ] Integration tests updated if module wiring changed
[ ] Regression tests run for all affected areas — all passing, or failures
    explicitly reported and blocking
[ ] Documentation updated per the update matrix (not more, not less)
[ ] CHANGELOG.md entry added
[ ] No known TODOs or placeholder code left silently — flagged if any remain
[ ] Any new/changed conditional gating a file, resource, or write operation
    has been explicitly read back in plain language to confirm it means what
    it's supposed to mean (catches inverted-logic bugs)
[ ] Any failure/edge path in new or changed code fails loudly (throws, logs,
    or returns a checkable invalid value) rather than silently
[ ] No secrets/credentials introduced in this change — diff scanned
[ ] Any new handling of personal/sensitive data has been flagged for my
    review, not decided unilaterally
```

Trivial fixes can skip most of this (see the playbook's "scale to size of
change" rule) — but the agent should say *which* items it's skipping and why,
not silently shorten the checklist.

---

## Part 3 — A few more things worth having, now that the system's this complete

- **Semantic versioning (semver)** — if you ever expect other people (or even
  future-you) to depend on a specific version's behavior, adopt
  MAJOR.MINOR.PATCH now rather than later. Cheap to start, painful to
  retrofit. Ties directly into RELEASE_NOTES.md.
- **A LICENSE file** — even for a personal/internal tool, worth deciding
  explicitly (private/proprietary vs. open) rather than leaving it undefined.
- **Dependency awareness** — when the agent adds a new library/package,
  it should note what it is and why, in CHANGELOG.md or DECISIONS.md if it's
  a meaningful addition — not just silently added to a package file.
- **A lightweight CI thought, even if manual for now** — even without full
  pipeline automation, having "run unit + regression tests" as a documented
  manual step before pushing is worth writing down in TESTING.md so it's not
  just tribal knowledge in your head.
- **"Flaky test" handling rule** — worth stating once: if a test fails
  intermittently, that gets investigated and fixed, never just re-run until
  it passes and ignored.

Nothing above needs to be built today — but they're the kind of gaps that
don't bite you until a project's a year old, so better to have the rule
written down now while it costs nothing.

---

## Part 4 — Add to the kickoff prompt (Part 5 of the playbook)

Append this paragraph to that template:

```
Also read testing-strategy-and-definition-of-done.md. Apply its Definition
of Done checklist before marking any non-trivial task complete, and write
unit tests (happy path, empty/missing input, malformed input) for every new
or changed function — not just regression tests at the pipeline level.
Treat silent failure as a defect: any code path handling unexpected input
must fail loudly, not produce quietly wrong output. Flag untested high-risk
legacy code as its own task rather than waiting for an unrelated change to
touch it. Explicitly sanity-check any inverted/negated condition guarding a
file, resource, or write operation. Never commit secrets or credentials —
scan diffs before finalizing. Flag any handling of personal or sensitive
data for my review rather than deciding policy yourself.
```
