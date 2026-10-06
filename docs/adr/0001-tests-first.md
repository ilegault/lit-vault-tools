# ADR 0001: Tests first

**Status:** Accepted

## Context

This repo follows a tests-first discipline: tests are written from the
acceptance criteria before any implementation begins.  A test that has never
been seen to fail is not known to work.

## Decision

All implementation work must begin with a failing test.  The gate script
`scripts/check_tests_first.py` enforces this in CI.

## Consequences

- Workers are slower on the first commit but the feedback loop is tighter.
- The acceptance criteria become executable specifications.
- No `skip`, `skipif`, or `xfail` markers are allowed on tests written for this
  repo's own tickets.
