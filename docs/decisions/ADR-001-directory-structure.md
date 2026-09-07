# ADR-001: Repository Architecture and Agent Memory Layout

- **Status**: Accepted
- **Date**: 2026-09-07

## Context
We need a structure to store configuration, automation scripts, and progressive learnings to replicate a customized Kubuntu setup on future machines, while enabling AI agents to read and maintain documentation without context window bloat.

## Decision
1. Use `AGENTS.md` and `GEMINI.md` as the high-level routing file loaded into agent context.
2. Separate procedural agent workflows into `.agents/skills/` to leverage Antigravity's progressive disclosure (token-efficient).
3. Enforce script guidelines via `.agents/rules/`.
4. Keep learning logs atomic in `docs/learnings/` following `TEMPLATE.md`.
5. Organize automation into sequential stages in `scripts/` driven by a top-level `bootstrap.sh`.

## Consequences
- Agents understand the repo immediately upon session start.
- Scripts remain modular and testable individually.
- Learnings remain searchable and atomic.
