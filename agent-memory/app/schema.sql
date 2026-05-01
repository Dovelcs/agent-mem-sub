PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL DEFAULT 'note',
  scope TEXT NOT NULL DEFAULT 'global',
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL DEFAULT '',
  related_doc_ids TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0.8,
  importance REAL NOT NULL DEFAULT 0.5,
  use_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_used_at TEXT,
  expires_at TEXT,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL DEFAULT '',
  doc_type TEXT NOT NULL DEFAULT '',
  project TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT '',
  customer TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  checksum TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  heading TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  source_kind TEXT NOT NULL DEFAULT '',
  evidence_level TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS key_values (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  namespace TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL DEFAULT '{}',
  tags TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(namespace, key)
);

CREATE INDEX IF NOT EXISTS idx_memories_status_importance
  ON memories(status, importance DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_type_scope
  ON memories(type, scope, status);
CREATE INDEX IF NOT EXISTS idx_memories_updated
  ON memories(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_path
  ON documents(path);
CREATE INDEX IF NOT EXISTS idx_documents_project
  ON documents(project, platform, customer);
CREATE INDEX IF NOT EXISTS idx_documents_checksum
  ON documents(checksum);
CREATE INDEX IF NOT EXISTS idx_chunks_document
  ON document_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_chunks_path
  ON document_chunks(path);
CREATE INDEX IF NOT EXISTS idx_key_values_namespace_key
  ON key_values(namespace, key);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
USING fts5(title, content, tags, content='memories', content_rowid='id');

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts
USING fts5(heading, content, path, tags, content='document_chunks', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, title, content, tags)
  VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
  VALUES ('delete', old.id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
  VALUES ('delete', old.id, old.title, old.content, old.tags);
  INSERT INTO memories_fts(rowid, title, content, tags)
  VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON document_chunks BEGIN
  INSERT INTO document_chunks_fts(rowid, heading, content, path, tags)
  VALUES (new.id, new.heading, new.content, new.path, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON document_chunks BEGIN
  INSERT INTO document_chunks_fts(document_chunks_fts, rowid, heading, content, path, tags)
  VALUES ('delete', old.id, old.heading, old.content, old.path, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON document_chunks BEGIN
  INSERT INTO document_chunks_fts(document_chunks_fts, rowid, heading, content, path, tags)
  VALUES ('delete', old.id, old.heading, old.content, old.path, old.tags);
  INSERT INTO document_chunks_fts(rowid, heading, content, path, tags)
  VALUES (new.id, new.heading, new.content, new.path, new.tags);
END;
