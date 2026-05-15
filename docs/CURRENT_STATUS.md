# Current Status

This document records the current archive baseline before moving beyond the
Phase 1 prototype.

## Repository Posture

- This repository is a private snapshot archive of MIT-licensed
  `claude-code-viewer` code plus the Python `cc_history` prototype.
- It is intentionally detached from the upstream Git history and should not be
  pushed to upstream remotes.
- Active GitHub Actions workflows are disabled in the repository tree. The
  original upstream workflow files are preserved under
  `docs/upstream-github-workflows/` for reference only.
- MIT license attribution must remain in place.
- Real Claude logs, NAS-derived data, personal information, `.env` files,
  caches, and Python bytecode must not be committed.

## Validation Baseline

Last local validation:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check src/cc_history tests
uv run --extra dev ruff format --check src/cc_history tests
```

Result:

- `pytest`: 40 tests passed
- `ruff check`: all checks passed
- `ruff format --check`: 37 files already formatted

Before committing, still run:

```bash
git ls-files | rg 'claude-logs|dev-private-share|__pycache__|\.pyc|\.env'
```

At this baseline it reports:

- `.env.local.sample`
- `.envrc`

These are not production secrets by themselves, but they must be reviewed
before any commit that touches environment-related files.

## Implemented Scope

### Phase 1: MVP

Status: complete.

Implemented:

- FastAPI application entry point and CLI script.
- Pydantic-based JSONL parsing with error entries for invalid lines.
- User, project, session, and conversation drilldown.
- API endpoints for users, projects, sessions, session entries, and search.
- Jinja2 web UI for browsing users, projects, sessions, and conversations.
- Tool calls and parse errors are visible in the session view.
- Local-only SQLite cache path via `CC_CACHE_DIR`.

### Phase 2: Detailed Display And Search

Status: substantially implemented.

Implemented:

- Structured content blocks for text, thinking, tool use, tool result,
  tool reference, image, and document content.
- Structured display for common tools such as Bash, Read, Write, Edit,
  MultiEdit, TodoWrite, Grep, Glob, LS, Task, and Agent.
- Thinking blocks, inline base64 images, document content, and unknown content
  fallback rendering.
- Edited-file extraction for session detail pages.
- SQLite FTS5 message index with session metadata.
- Search API and HTMX search UI with user filtering.
- Index skipping based on source mtime and size.

Remaining candidates:

- More complete treatment of every Claude Code JSONL edge case from real logs.
- Better ranking, snippets, and query syntax for FTS.
- Dedicated UI for long tool outputs, large diffs, and very large images.

### Phase 3: Multi-User Support

Status: partially implemented.

Implemented:

- Multi-user root scanning:
  `CC_NAS_ROOT/<user>/claude-logs/projects/<project>/<session>.jsonl`
- Single-user `CLAUDE_CONFIG_DIR` style layout detection:
  `CC_NAS_ROOT/projects/<project>/<session>.jsonl`
- User-filtered search.
- Overview, user, and project statistics.
- Basic password authentication through `CC_AUTH_PASSWORD`.
- Optional watchdog-based index refresh controlled by `CC_WATCH_ENABLED`.

Current operating policy:

- `CC_WATCH_ENABLED=false`
- Manual reload and on-demand indexing are acceptable for this archive phase.

Remaining candidates:

- Production-grade authentication and per-user authorization.
- Stronger admin/operator UI for indexing status.
- A deliberate decision on whether file watching is worth keeping.

### Phase 4: Manual Knowledge Curation

Status: initial web-viewer support has started.

Implemented:

- Local SQLite tables for session annotations and session tags.
- Deterministic auto-label backfill for every discovered session.
- Session detail form for title override, notes, tags, favorite/archive state,
  review status, and knowledge scope.
- Session list badges for favorites, tags, review status, scope, and archived
  state.
- Initial `/agent-context` preview page that builds Markdown from matching
  candidate/reviewed annotations.
- Project pages link to the Agent Context builder for that project.
- Project pages and the Agent Context page can refresh auto labels without
  overwriting manual notes.
- Annotation data stays in the local cache DB and never writes back to JSONL.

Design intent:

- Daily summaries should remain intake material, not the knowledge base itself.
- Every history should get baseline labels so unreviewed sessions remain
  discoverable.
- Durable knowledge should move through review states before it is used in an
  Agent Context Pack.
- The current session-level metadata is deliberately small so later knowledge
  items can be more granular without breaking the viewer.

## Recommended Next Step

Treat this point as the baseline for continuing Phase 4.

The next implementation slice should be small and user-visible:

1. Add a project-level annotation overview or inbox.
2. Add "Add to context" actions for session and search result rows.
3. Add saved context packs and a review/export history.
4. Keep all generated context local unless explicitly exported.

This creates the first useful bridge from "history viewer" to "knowledge
manager" without requiring LLM extraction yet.
