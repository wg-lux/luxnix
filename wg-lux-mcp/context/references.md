# Engineering references

## REF-0001: Effective context engineering for AI agents

Source: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

Published: 2025-09-29

Topics: context engineering, progressive disclosure, compaction, persistent state

Principles adopted by this project:

- Context is finite and should be treated as an attention budget.
- Prefer the smallest set of high-signal information sufficient for a task.
- Retrieve detailed information just-in-time rather than eagerly.
- Keep MCP tools narrowly scoped and non-overlapping.
- Prefer progressive disclosure when navigating repositories.
- Preserve long-term state outside the model context.
- Compact completed work into decisions, outcomes, and unresolved issues.
- Drop redundant historical tool output.
- Preserve architectural decisions and unresolved bugs during compaction.
