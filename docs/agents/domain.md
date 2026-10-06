# Domain docs

How engineering skills should consume this repo's domain documentation.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the design and vocabulary of the vault tools:
  saved paper, stub, focus, trail, Enrich, Explore, stub retirement, the note
  ownership model. If a term here and the code disagree, flag it; do not silently
  pick a side.
- **`docs/adr/`** — read the ADRs that touch the area you are about to work in.
  They are binding, not background.

If any of these files do not exist, proceed silently.

## File structure

```
/
├── AGENTS.md          conventions + the ACTIVE-PLAN pointer
├── CLAUDE.md          one line: @AGENTS.md
├── CONTEXT.md         design + glossary
├── docs/adr/          binding decisions
├── docs/agents/       how agents work this repo
├── .scratch/          specs and tickets, tracked in git
├── src/lit_vault_tools/
└── tests/             fixtures/ holds saved real API responses
```

## Use the glossary's vocabulary

When your output names a domain concept, use the term as `CONTEXT.md` defines it.
A **saved paper** is one that is in Zotero; a **stub** is a temporary preview in
`_explore/`. Never call a stub a "paper note" or a saved paper a "stub".

If a concept is not in the glossary: either you are inventing language (reconsider),
or there is a real gap (note it).

## Flag ADR conflicts

If your output contradicts an ADR, surface it explicitly rather than silently
overriding it.
