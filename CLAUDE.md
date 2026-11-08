# CLAUDE.md

## Token budget
- Follow the token-saver skill on any multi-step task. Small one-off tasks: just do them.
- Read only the files and line ranges needed; edit, don't rewrite.
- Use subagents (Sonnet/Haiku) for broad searches and log or doc reading.
- Opus for planning and hard bugs, Sonnet for building, Haiku for chores.
- Before /clear or at a natural break, write HANDOFF.md.
- When compacting, keep: the plan, decisions, failing tests, changed file paths.
- Never shorten the deliverable itself to save tokens.
