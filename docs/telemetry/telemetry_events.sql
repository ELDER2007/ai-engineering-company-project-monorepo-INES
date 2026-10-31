-- Telemetry events table for Supabase (SQL Editor -> New query -> Run).
-- Same as services/api/telemetry/models.py; the API also creates it at startup if it is missing.
-- Immutable: the API only INSERTs. 8 columns, 3 indexes (timestamp, event_type, GIN on tags).

CREATE TABLE IF NOT EXISTS telemetry_events (
	event_id VARCHAR(36) NOT NULL,
	event_type VARCHAR(64) NOT NULL,
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
	service VARCHAR(16) NOT NULL,
	user_id VARCHAR(64),
	session_id VARCHAR(36),
	environment VARCHAR(16) NOT NULL,
	tags JSONB NOT NULL,
	PRIMARY KEY (event_id)
);
CREATE INDEX IF NOT EXISTS ix_telemetry_events_timestamp ON telemetry_events (timestamp);
CREATE INDEX IF NOT EXISTS ix_telemetry_events_event_type ON telemetry_events (event_type);
-- GIN: searches inside the JSONB, e.g. WHERE tags @> '{"office": "miami"}'
CREATE INDEX IF NOT EXISTS ix_telemetry_events_tags ON telemetry_events USING GIN (tags);

-- The API is the only writer. Supabase exposes tables through its public REST API: keep it closed.
ALTER TABLE telemetry_events ENABLE ROW LEVEL SECURITY;
