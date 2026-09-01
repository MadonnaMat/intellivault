-- Registration no longer pre-creates a users row (that row was hijackable
-- before the ceremony finished). The pending email + display name now ride on
-- the challenge and the user is created only on a verified finish.
ALTER TABLE webauthn_challenges ADD COLUMN email        TEXT;
ALTER TABLE webauthn_challenges ADD COLUMN display_name TEXT;

-- Support the opportunistic "delete everything past its TTL" sweeps.
CREATE INDEX webauthn_challenges_expires_at_idx ON webauthn_challenges (expires_at);
CREATE INDEX sessions_expires_at_idx ON sessions (expires_at);

-- Case-insensitive email uniqueness (the plain UNIQUE from 0001 stays as a
-- fast-path and NOT NULL guard).
CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email));
