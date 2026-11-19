PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS links (id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id), target TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (message_id TEXT NOT NULL REFERENCES messages(id), event TEXT NOT NULL CHECK(event IN ('open','click')), occurred INTEGER NOT NULL, PRIMARY KEY(message_id,event));
