CREATE TABLE IF NOT EXISTS sessions (
  id TEXT NOT NULL,
  user TEXT NOT NULL,
  project TEXT NOT NULL,
  project_decoded TEXT,
  file_path TEXT NOT NULL,
  first_message_at TEXT,
  last_message_at TEXT,
  message_count INTEGER NOT NULL DEFAULT 0,
  custom_title TEXT,
  ai_title TEXT,
  source_mtime REAL NOT NULL,
  source_size INTEGER NOT NULL,
  indexed_at TEXT NOT NULL,
  PRIMARY KEY (user, project, id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_project ON sessions(user, project);
CREATE INDEX IF NOT EXISTS idx_sessions_last_message ON sessions(last_message_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  session_id UNINDEXED,
  user UNINDEXED,
  project UNINDEXED,
  uuid UNINDEXED,
  role,
  text,
  timestamp UNINDEXED,
  tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS session_annotations (
  session_id TEXT NOT NULL,
  user TEXT NOT NULL,
  project TEXT NOT NULL,
  manual_title TEXT,
  note TEXT NOT NULL DEFAULT '',
  is_favorite INTEGER NOT NULL DEFAULT 0,
  is_archived INTEGER NOT NULL DEFAULT 0,
  review_status TEXT NOT NULL DEFAULT 'unreviewed',
  knowledge_scope TEXT NOT NULL DEFAULT 'unset',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user, project, session_id)
);

CREATE INDEX IF NOT EXISTS idx_session_annotations_project
  ON session_annotations(user, project);

CREATE TABLE IF NOT EXISTS session_tags (
  user TEXT NOT NULL,
  project TEXT NOT NULL,
  session_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  category TEXT NOT NULL DEFAULT 'topic',
  created_at TEXT NOT NULL,
  PRIMARY KEY (user, project, session_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_session_tags_project
  ON session_tags(user, project);

CREATE INDEX IF NOT EXISTS idx_session_tags_tag
  ON session_tags(tag);
