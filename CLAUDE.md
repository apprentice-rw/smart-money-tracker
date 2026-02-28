# Claude Code Instructions — Smart Money Tracker

## Superpowers Skills

Before acting on any task, scan the list below and invoke every skill that applies.
Even a 1% chance of relevance = invoke it. No rationalising ("it's too simple", "I know what to do").

### Decision guide

| Situation | Skill to invoke |
|---|---|
| Starting any task — check which other skills apply | `superpowers:using-superpowers` |
| About to add/change/build any feature or behaviour | `superpowers:brainstorming` |
| Have a spec or requirements for a multi-step task | `superpowers:writing-plans` |
| Executing a written plan in the current session | `superpowers:subagent-driven-development` |
| Executing a written plan in a fresh session | `superpowers:executing-plans` |
| Hit a bug, test failure, or unexpected behaviour | `superpowers:systematic-debugging` |
| Implementing any feature or bugfix | `superpowers:test-driven-development` |
| About to claim something is done, fixed, or passing | `superpowers:verification-before-completion` |
| Completed a feature or fix batch | `superpowers:requesting-code-review` |
| Received code review feedback | `superpowers:receiving-code-review` |
| Implementation complete, ready to merge/PR | `superpowers:finishing-a-development-branch` |
| 2+ independent tasks that don't share state | `superpowers:dispatching-parallel-agents` |
| Need isolated environment for feature work | `superpowers:using-git-worktrees` |
| Creating or editing a skill file | `superpowers:writing-skills` |

### Mandatory minimums for every coding task

1. **`superpowers:brainstorming`** — before writing any code
2. **`superpowers:verification-before-completion`** — before every commit
3. **`superpowers:requesting-code-review`** — after completing a feature or fix batch
