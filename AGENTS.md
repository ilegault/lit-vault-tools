# AGENTS.md — orientation for AI sessions working on lit-vault-tools

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<effort>/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` at the repo root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.

lit-vault-tools is two manually-run commands for the developer's literature-review
Obsidian vault: **`enrich`** fills graph metadata into saved paper notes, and
**`explore`** writes temporary stub previews of one paper's references and
citations into `_explore/`. **Read `CONTEXT.md` before touching code** — it is the
design, not background.

**These tools write into notes the developer has typed into by hand.** Destroying a
paragraph of someone's reading notes is not a cosmetic bug. That is why the
ownership rules below are strict, and why a test made green by editing it is worse
than a red one.

---

## 1. Quick facts

| | |
|---|---|
| Language / runtime | Python 3.12+ (dev machine is Windows); CI runs 3.14 |
| Entry point | `lit-vault enrich ...` / `lit-vault explore ...` → `src/lit_vault_tools/cli.py:main()` (created by the first tickets) |
| Data sources | Semantic Scholar (Explore), OpenAlex (Enrich), Crossref + OSTI (fallbacks). See CONTEXT.md |
| Tests | `pytest`, fully offline: saved real API responses in `tests/fixtures/`, temporary vault directories |
| Secrets | `OPENALEX_API_KEY`, `S2_API_KEY` from a local `.env` (gitignored). Never in the repo |
| Repo | `master`; remote `origin` = `github.com/ilegault/lit-vault-tools`. CI on push and PR |

```
# setup
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

# the gate, in the order CI runs it
ruff check .
python scripts/check_tests_first.py
pytest -q
```

---

## 2. Layers

```
config         constants and tunables (caps, trail length, folder names). No I/O.
domain         pure functions: parse/serialize frontmatter regions, normalize DOIs,
               rank citations, name stubs and author notes, decide what to write.
               Same input, same output. No network, no disk.
clients        OpenAlex / Semantic Scholar / Crossref / OSTI. Return plain data.
               The only code that touches the network.
vault          read and write note files. The only code that touches the vault.
commands       enrich and explore: wire clients → domain → vault.
cli            argument parsing only.
```

**Imports flow downward only:** `cli → commands → (vault, clients) → domain → config`.

### Invariants the design rests on

1. **Ownership.** Zotero Integration owns its fields, the script owns the
   enrichment keys listed in CONTEXT.md, the developer owns the note body. The
   script never writes outside its own keys, and never touches the body.
2. **Never rename, move or delete a saved paper note.** The only deletions are
   inside `_explore/`: wiping old stubs, and retiring a stub whose paper is saved.
3. **Match by ID, never by filename or name.** Papers by DOI / `openalex_id` /
   `s2_id`; authors by OpenAlex author ID.
4. **Idempotent.** Same data in, same file out, byte for byte. `enriched_on`
   changes only when an enrichment value changed.
5. **Nothing runs in the background.** No watchers, no daemons, no scheduled runs.
6. **Never write `location: 0,0`.** Omit `location` when coordinates are unknown.

---

## 3. Testing

- **Fixtures are real.** Save real API responses (OpenAlex is CC0) into
  `tests/fixtures/` and fake the network with them. Never hand-invent a response
  shape — the shapes in CONTEXT.md were verified against the real APIs.
- **Use a temporary vault directory** (`tmp_path`) with real note files. Assert on
  the files written: their frontmatter, their bytes, what was deleted, and what was
  *not* touched.
- **Test behaviour, not shape.** Good: "a note's body is byte-identical after
  `enrich`", "re-running `enrich` changes nothing", "a stub whose DOI matches a
  saved paper is deleted and its links point at the saved note". Not: "the
  function exists".
- **Assert the absence of a write** where that is the point — that a saved note was
  not renamed, that nothing outside `_explore/` was deleted.
- Nothing in the suite may reach the network, a real vault, or a real API key.

---

## 4. Working agreement for AI sessions

- Read CONTEXT.md and the module docstring before editing a module. Docstrings
  explain *why*, not what.
- Use `logging.getLogger(__name__)`; never `print()` in library code (the CLI may
  print its own output).
- New tunable → `config`. New pure rule → the domain module that owns it.
- Roles, never names: "the developer", never a person's name.

### Fix or escalate — never mute a failing test

Binding rule, from `docs/adr/0001-tests-first.md` (read it
before touching a failing test): **a failing test is fixed or escalated, never
muted.** That means never marking it `xfail`, never deleting or weakening the
assertion, never loosening a tolerance, and never narrowing its inputs until it
happens to pass. Those are all the same move — making the test stop reporting the
problem instead of fixing the problem.

**When you cannot fix a failing test, stop and escalate. Do not guess at a design
decision and do not work around it.** The escalation procedure has four steps:

1. **Commit your finished work to the branch.** Whatever is done and correct so
   far is preserved, not lost.
2. **Set the ticket's own `Status:` line to `blocked`.**
3. **Append a comment under the ticket's `## Comments` heading**: what you
   attempted, what failed, and what needs a human decision.
4. **Open the pull request as a draft.** Master is not touched.

The ticket file travels with the branch, so the draft PR plus its failing CI run
*is* the report — a planning session can read the ticket directly off the branch
with no separate handoff. This is also why the report must be written into the
ticket file itself, in `.scratch/`, and **not** anywhere under `.claude/` or in
`Claude outputs/`: those are gitignored, so anything written there never gets
pushed and no reviewer — human or AI — will ever see it.

### Tests-first CI check and documented escape

CI enforces that any pull request or commit modifying application code under
`src/` must also modify tests under `tests/` (`scripts/check_tests_first.py`).
Changes touching only documentation (`docs/`), scripts (`scripts/`), CI
configuration (`.github/`), or tests (`tests/`) pass automatically.

When a change touching `src/` genuinely does not require test additions (a
comment-only clarification, a pure structural move fully covered by existing
tests), declare an explicit and visible escape reason:

- **Commit message or PR text**: include `[no-test-needed: <reason>]`,
  `[tests-exempt: <reason>]`, or `[skip-test-gate]`.
- **PR label**: apply `tests-exempt` or `skip-test-gate`.

The reason is recorded in the PR history and visible during review. Silent
bypassing is not possible.

### Implementing a ticket — the protocol

This repo is worked by more than one agentic tool, and not all of them have slash
commands. Anything an implementer must obey lives here, in this file, because this
file is the only thing every tool reads. A rule that lives only in a command binds
only the tool that has that command.

1. Read the `ACTIVE-PLAN` block below. It names the ticket set and which tickets
   are unblocked. Read the ticket file, and read every ADR it references.
2. **Work the frontier.** Never start a ticket whose `Blocked by:` line names an
   unfinished ticket. If everything unblocked is a human task (an Obsidian UI step, a GitHub setting), say so and stop — do not claim it and do not invent work
   around it.
3. Set the ticket's `Status:` line to `in-progress` before you start, and to
   `done` when it lands. Use exactly those words. The status vocabulary is
   `ready-for-agent` / `in-progress` / `done` / `blocked` / `ready-for-developer`
   (`human-task` is a legacy spelling the dispatcher cannot read), and
   nothing else — three spellings of "finished" make the frontier unreadable.
4. One ticket per branch. One pull request per ticket. Never commit to `master`.
5. Run the full gate before you start and before you open the PR:
   `ruff check .`, `python scripts/check_tests_first.py`, `pytest -q`.
   **Zero failures before you push.** Not "the failures look unrelated" — zero.
6. **A failing test is fixed or escalated, never muted.** No `xfail`, no deleted
   or weakened assertions, no loosened tolerances, no narrowed inputs.
   `docs/adr/0001-tests-first.md` is binding.
7. When you cannot fix a failing test, escalate in four steps: commit the finished
   work to the branch; set `Status:` to `blocked`; append what you attempted, what
   failed, and what needs a human decision under `## Comments`; open the pull
   request as a **draft**.
8. **The escalation report goes in the ticket file, under `.scratch/`.** Never
   under `.claude/` or `Claude outputs/` — both are gitignored.
9. Update the module docstring's reasoning when you change behaviour.
10. **Never run against a real vault or the live APIs.** Running the tools on the vault is
    the developer's manual step after merge. Do not add anything to a ticket that assumes it.
11. **After pushing, watch CI and fix what it finds** — up to two fix-and-push
    cycles, then escalate. See the section directly below; it is binding.

### Watching CI, and fixing what it finds

**Do not open the pull request and walk away.** The session that wrote the code is
by far the cheapest place to fix it: it still holds the ticket, the ADRs, the diff
and its own reasoning. The same failure found an hour later costs a fresh session
that has to re-read all of that before it can even read the error message.

After pushing the branch and opening the PR:

```
gh pr checks --watch --fail-fast
```

`--watch` blocks until every check resolves; `--fail-fast` returns as soon as one
fails. The gate here is three checks and the suite is small, so a run is
typically a couple of minutes. Wait it out — a slow check is not a reason to stop watching.

If `gh` is not installed or not authenticated, install it (`winget install
GitHub.cli` on Windows, then `gh auth login`). If you genuinely cannot reach it,
**say plainly that CI was not observed.** Never report a run green that you did
not watch resolve.

#### When it goes green

Tick the acceptance criteria individually, set the ticket's `Status:` to `done`,
commit the ticket file, report what landed, and stop. Do not start the next ticket.

#### When it goes red

**Read the failure before theorising about it.**

```
gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId'
gh run view <run-id> --log-failed
```

`--log-failed` prints only the steps that failed. **Never pull the full run log
into context** — on this repo that is thousands of lines of passing tests, and it
tells you nothing the failed-step output does not.

Then fix and push again, under a budget.

#### The budget: two fix-and-push cycles, then escalate

Not three. Not "one more, I think I have it this time." A third attempt at the same
failure means the diagnosis is wrong, and the cost of being wrong a third time is
higher than the cost of a person spending five minutes on it.

Each cycle is: read the failed-step log, diagnose the **root cause**, fix it, commit
with a message naming what the failure actually was, push, watch again.

#### Classify the failure, and say which you concluded

State your classification in the commit message. A fix whose reasoning is not
written down is indistinguishable from a guess that happened to work.

- **A real defect** — the test is right, the code is wrong. Fix the code. This is
  the test doing its job; it is good news.
- **A harness defect** — the test asserts something the code never promised, or
  models the world wrong (a fake that does not behave like the real thing, a
  fixture that leaks). Fix the test, and say in the commit message why the old
  assertion was wrong. **This is the category an agent under pressure abuses**, so
  the bar is: you can state what the test should have asserted instead, and it
  still fails if the behaviour is wrong.
- **An environment difference** — passes locally, fails in CI. A Python version difference, a missing entry in
  `requirements-dev.txt`, a path separator, a test that reached for a real
  API key or a real vault the runner does not have. Fix
  the cause. "It's environmental" is a diagnosis, not an excuse, and it is never a
  reason to skip or condition the test on CI.

#### The loop makes muting more tempting, not less

You can now watch the build go red and push again thirty seconds later. That is
precisely the situation `docs/adr/0001-tests-first.md` was
written for. Under time pressure the cheapest-looking move is to edit the test
rather than the code, and it is the one move that is always forbidden: no `xfail`,
no `skip`, no deleted or weakened assertion, no loosened tolerance, no narrowed
input, no `try/except` swallowing the error the test existed to surface.

**If you are editing a test so that it stops reporting a problem you have not
fixed, you are escalating, not fixing.** Stop and escalate.

#### When the budget runs out

Escalate in the four steps — commit the finished work, set the ticket's `Status:`
to `blocked`, append to `## Comments`, convert the PR to a draft
(`gh pr ready --undo`). In the ticket comment, record:

- what CI said, quoted from the failed-step log, not paraphrased
- what you concluded each attempt, and what each attempt changed
- why you think it is still red
- what decision you need from a human

The draft PR plus its failing run **is** the report. Nothing else needs writing,
and nothing goes anywhere a reviewer cannot reach.

#### A red check you did not cause is not yours to fix silently

If `master` is already failing, or a check fails for a reason unrelated to your
diff, say so and do not bury the fix inside your ticket's branch. A refactor with
someone else's bug fix smuggled into it cannot be reviewed.


<!-- ACTIVE-PLAN:START -->
## Active implementation plan

_Written by the planning model on 2026-10-07 00:57. Implement this. If something in it is wrong, say so before changing course._

# Plan: lit-vault-tools v1 (enrich + explore)

This is a pointer, not the work.

- **Spec:** `CONTEXT.md` (no separate spec.md). Decisions 12-16 (round 3) were added while ticketing; decision 12 was amended and 17-18 added on 2026-10-06 after the real fixtures were captured.
- **Binding:** `docs/adr/0001-tests-first.md`; AGENTS.md layers and invariants.
- **Tickets:** `.scratch/lit-vault/issues/01-*.md` through `22-*.md`. Conventions: `docs/agents/issue-tracker.md`.
- **New / changed terms:** institution notes use `type: institution` and `institution_type`; HTTP via stdlib **`http.client`** (not `urllib`, which breaks the case-sensitive `x-api-key` header) behind an injectable `Transport`; `ReferencesHidden` = Semantic Scholar answered a references page with `"data": null` (publisher hid them); reference fallback = Crossref reference DOIs looked up via S2 `/paper/batch`; geo cache outside the vault (`LIT_VAULT_CACHE_DIR`); temporary links live only in `_explore/_focus.md`.

## Next

01-05, 13 and 14 are done; real fixtures are in `tests/fixtures/`.
Start **06** (agent): it builds the shared `http.client` transport and gates 07, 08, 09 and 15.
**20** is `ready-for-developer` (capture `s2_batch_by_doi.json` with the live key). Never claim it; 21 waits on it.

## Dependency graph

```
01 -> 02 -> 03                                  (done)
01 -> 04                                        (done)
05 (developer, done) -> 06 (also needs 04) -> 07, 08
02,03,06 -> 09 -> 10 (also 04, 07)
08,09,15 -> 11
09 -> 12
01,04 -> 13 -> 14 (also 02)                     (done)
05,06,13 -> 15 -> 16 (also 03, 14) -> 17, 18
09,16 -> 19
20 (developer: capture fixture) + 15 -> 21
08,16,21 -> 22
```

17, 18 and 22 all extend `commands/explore.py`; expect to rebase on whichever lands first.

## Requirements to treat as binding, not preferences

- No runtime dependencies: no YAML library, no `requests`. HTTP is `http.client`; never `urllib` (header case). Frontmatter is edited line-wise so non-owned lines and the body stay byte-identical.
- A saved paper note's body is never touched; nothing outside `_explore/` is ever deleted; notes are never renamed.
- Match by DOI / `openalex_id` / `s2_id`, never by filename. Never write `location: 0,0`.
- Idempotent: second run is byte-identical and `enriched_on` moves only when a value changed.
- Explore fetches everything before wiping `_explore/`; a failed fetch leaves `_explore/` untouched.
- A hidden reference list (`"data": null`) is `ReferencesHidden`, never an empty list.
- Never use real keys, the live APIs, or a real vault. Fixtures are real captured responses (tickets 05, 20); never invent a response shape.

## Deliberately not in this set

Unpaywall, TDS extraction, any watcher or auto-run, permanent storage of unsaved papers, the Obsidian manual setup checklist (CONTEXT.md), `.env` handling beyond `KEY=VALUE` lines, and an OpenAlex-based reference fallback (Crossref is the fallback; OpenAlex reference IDs would need extra lookups).
<!-- ACTIVE-PLAN:END -->

## Implementation Protocol

<!-- ticket-engine-bootstrap: implementation-protocol -->

Tickets are implemented following the engine's runner-agnostic skill.
See `src/ticket_engine/resources/ticket_skill.md` in `ilegault/ticket-engine`.

Key rules for all workers:
- Write tests from the acceptance criteria **before** any implementation.
- Cores are pure: no I/O in dispatch, integrity, or bootstrap cores.
- Every tunable lives in `.ticket-engine.toml`, never hardcoded in logic.
- Use `logging.getLogger(__name__)`; never `print()` in library code.
- One ticket, one branch, one PR. Never commit to the default branch.

## Roles, Not People

<!-- ticket-engine-bootstrap: roles-not-people -->

Never write real people's names, Slack IDs, or emails in code, commits,
tickets, or documentation. Refer to **roles** ("the approver", "a buyer",
"the developer"). See `ilegault/ticket-engine` ADR 0002.
