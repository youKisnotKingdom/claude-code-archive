# Agent Context Handoff

This document describes how session history and extracted knowledge should be
handed to a new coding agent session.

The goal is not to dump raw logs into an agent. The goal is to build a compact,
traceable context package that helps the agent follow project conventions,
avoid known pitfalls, and reuse past solutions.

## Core Concept

Introduce an **Agent Context Pack**.

An Agent Context Pack is a generated Markdown document assembled from selected
sessions, manual annotations, reviewed knowledge items, and project metadata.
It can be copied into a new agent session, exported as `AGENT.md` or
`CLAUDE.md`, or later served through MCP.

The pack should always answer these questions:

- What project or task scope is this for?
- What rules or conventions must the agent follow?
- What past sessions are relevant?
- What decisions, pitfalls, commands, and file patterns should the agent know?
- Where can a human verify each claim?

## Knowledge Shape

The system should not treat daily activity as a pile of summaries. Daily review
is only an intake step.

Use this progression:

1. **Raw event**: JSONL messages, tool calls, edited files, command outputs.
2. **Observation**: A compact fact extracted from the raw event.
3. **Candidate**: A possible reusable lesson, classified by type and scope.
4. **Reviewed knowledge**: Human-approved knowledge that can be reused.
5. **Context pack item**: A reviewed item selected for a specific future agent
   task.

This keeps work logs, notes, and reusable knowledge separate.

Suggested candidate types:

| Type | Meaning |
| --- | --- |
| `decision` | A choice that should guide future work. |
| `pattern` | A repeatable approach that worked. |
| `pitfall` | A failure mode or trap to avoid. |
| `command` | A useful check or operational command. |
| `file-map` | Knowledge about important files or directories. |
| `follow-up` | Unfinished work that may affect future sessions. |
| `context-rule` | A rule suitable for AGENT.md or CLAUDE.md. |

Suggested scopes:

| Scope | Meaning |
| --- | --- |
| `private` | Useful only to one person and not shared by default. |
| `user` | A personal work pattern that can follow the user across projects. |
| `project` | Project-specific knowledge. |
| `org` | Shared convention or institutional knowledge. |

The first web-viewer implementation stores only session-level annotations,
tags, review status, and scope. That is intentional: it gives humans a way to
mark durable knowledge now, while leaving room for finer-grained knowledge
items later.

Every discovered session should also receive deterministic auto labels. These
labels are not trusted knowledge by themselves; they are discovery aids for the
review inbox and context builder. Manual tags must remain separate and should
not be overwritten by auto-label refreshes.

## Delivery Modes

### Phase 4: Manual Context Pack

Use only human-authored or human-selected data:

- Session tags
- Session notes
- Favorites
- Manually selected sessions
- Search result selections
- Edited files and command summaries extracted from existing JSONL

Output:

- Copyable Markdown preview in the UI
- Downloadable `AGENT.md`
- Source links back to session pages

This can be built before LLM extraction exists.

### Phase 5: Knowledge-Backed Context Pack

Use generated but human-reviewed data:

- Reviewed `knowledge_items`
- Session summaries
- Problems solved
- Approaches tried
- Reusable commands and snippets
- Similar sessions found by embedding search

Output:

- Same Markdown preview/export UI
- Optional inclusion of draft knowledge, off by default

### Phase 6: Project AGENT.md Generator

Use a stable template and structured data to produce a maintained project
context file.

Output:

- `AGENT.md` preview
- `CLAUDE.md` preview when desired
- Diff against the last generated version
- Manual edits before export

### Phase 7: MCP Or Hook Delivery

Serve the same context through machine-readable tools:

- `get_agent_context(project, task)`
- `search_knowledge(query, project, user)`
- `get_session_outline(session_id)`
- `get_relevant_sessions(query, project)`

This lets a new session request only the context it needs instead of receiving a
large static file every time.

## Recommended UI

### Navigation

Add a top-level `Agent Context` entry.

It should open a builder rather than a static page, because the useful context
depends on the next task.

### Context Basket

Add an "Add to context" action in these places:

- Search result rows
- Session list rows
- Session detail header
- Edited file list
- Future knowledge item rows

The selected items go into a persistent side tray named `Context Basket`.

Basket item types:

- Session
- Message anchor
- Edited file
- Tool result
- Tag
- Knowledge item
- Project

### Builder Page

Route:

```text
/agent-context
```

Initial implementation status:

- The page can generate a Markdown preview from session annotations.
- It filters by user, project, review status, knowledge scope, and archived
  state.
- It defaults to `candidate`/`reviewed` annotations with `project`/`org` scope.
- It copies Markdown client-side; it does not send context anywhere.

Main sections:

| Section | Purpose |
| --- | --- |
| Scope | Choose user, project, time range, tags, and status filters. |
| Sources | Show selected sessions, messages, knowledge items, and edited files. |
| Include | Toggle summaries, rules, pitfalls, commands, snippets, and source links. |
| Budget | Set approximate token or character budget. |
| Privacy | Redaction preview and raw-log inclusion controls. |
| Preview | Generated Markdown with source references. |
| Export | Copy Markdown, download `AGENT.md`, or save as a context pack. |

The builder should prefer summaries and reviewed knowledge. Raw messages should
be opt-in and visibly marked.

### Project Shortcut

On each project page, add:

```text
Create Agent Context
```

Default filters:

- current project
- reviewed knowledge only
- favorite sessions included
- archived sessions excluded
- last 30 to 90 days, configurable

### Session Shortcut

On each session page, add:

```text
Use This Session As Context
```

Default output:

- session title
- one-line reason to include it
- edited files
- command summary
- important notes and tags
- source link back to the session

## Context Pack Template

The generated Markdown should be stable and easy to scan:

````markdown
# Agent Context: <project or task>

## Scope

- User: <user or all>
- Project: <decoded project path>
- Generated: <timestamp>
- Source policy: reviewed knowledge + selected sessions

## Operating Rules

- <reviewed convention or manually selected rule>

## Known Pitfalls

- <pitfall>
  Source: <session link or knowledge item link>

## Useful Patterns

- <pattern>
  Source: <session link or knowledge item link>

## Relevant Past Sessions

- <title>
  Why relevant: <short reason>
  Files: <file list>
  Source: <session link>

## Commands And Checks

```bash
<command>
```

Source: <session link>

## Open Questions

- <questions the current context does not answer>
````

Source links are mandatory for generated claims. If a claim has no source, it
should stay out of the default pack.

## Data Model Sketch

Phase 4 can start with local SQLite tables:

```sql
CREATE TABLE context_packs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  scope TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  body TEXT NOT NULL,
  source_policy TEXT NOT NULL,
  token_estimate INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE context_pack_sources (
  id TEXT PRIMARY KEY,
  context_pack_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  user TEXT,
  project TEXT,
  session_id TEXT,
  uuid TEXT,
  knowledge_item_id TEXT,
  label TEXT,
  source_url TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_context_pack_sources_pack
  ON context_pack_sources(context_pack_id);
```

This is intentionally separate from the source JSONL files.

## Privacy And Safety Defaults

Default behavior:

- Do not include raw logs unless explicitly selected.
- Do not include archived sessions.
- Include only reviewed knowledge once Phase 5 exists.
- Show the exact source list before export.
- Keep generated context local unless the user explicitly saves or exports it.
- Never write back to the original JSONL files.

The UI should flag these content types before export:

- Environment variables and secrets
- Credentials
- Personal names or account identifiers
- Absolute private paths
- NAS paths
- Large raw tool outputs

## First Implementation Slice

Build the Phase 4 version first:

1. Add annotation tables for session notes, tags, favorites, archive state,
   review status, and knowledge scope.
2. Show and edit those annotations in the session web view.
3. Add `/agent-context` with source list, include toggles, and Markdown preview.
4. Add an "Add to context" action for sessions and search results.
5. Add an in-memory or local SQLite context basket.
6. Add saved context packs and export history.
7. Add download export.

This creates a useful agent handoff workflow before LLM extraction, embeddings,
or MCP are implemented.
