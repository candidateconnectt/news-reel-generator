# tools/

Reference repositories cloned for inspiration / install. None of these run automatically — pick what you want, install, and integrate.

## Already cloned

| Repo | Purpose | Install |
|------|---------|---------|
| `claude-code/` | Source of the **frontend-design** skill (Anthropic's design-direction prompt for Claude Code). Read `plugins/frontend-design/skills/frontend-design/SKILL.md`. | Plugin — install via Claude Code marketplace, or copy the skill markdown into your own `.claude/skills/` |
| `spec-kit/` | GitHub's **Spec-Driven Development** toolkit. The `specify` CLI bootstraps projects with `/speckit.constitution → /speckit.specify → /speckit.plan → /speckit.tasks → /speckit.implement`. | `cd spec-kit && pip install -e .` (requires Python ≥3.11) then `specify init` inside any project folder. Works with 30+ AI agents. |

## Other things to consider

See the catalog Claude produced alongside this folder — every entry has a senior-preferred alternative and the use case it covers.
