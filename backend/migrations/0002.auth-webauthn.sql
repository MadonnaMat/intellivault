-- Passwordless auth: WebAuthn passkey credentials, in-flight ceremony
-- challenges, and server-side sessions. `sessions.user_id` is the ownerId every
-- tenant-scoped query keys off.

-- A human-facing name for the passkey, shown on the account page.
ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE users ALTER COLUMN display_name DROP DEFAULT;

CREATE TABLE webauthn_credentials (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    credential_id BYTEA NOT NULL UNIQUE,
    public_key    BYTEA NOT NULL,
    sign_count    BIGINT NOT NULL DEFAULT 0,
    transports    TEXT[] NOT NULL DEFAULT '{}',
    aaguid        TEXT,
    name          TEXT NOT NULL DEFAULT 'Passkey',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ
);

CREATE INDEX webauthn_credentials_user_id_idx ON webauthn_credentials (user_id);

-- Short-lived challenge issued by a ceremony "begin" call and consumed (deleted)
-- by the matching "finish" call. The row id travels in the iv_ceremony cookie.
-- user_id is set for registration / add-passkey ceremonies (which user the new
-- credential belongs to) and NULL for a login ceremony.
CREATE TABLE webauthn_challenges (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    challenge  BYTEA NOT NULL,
    user_id    UUID REFERENCES users (id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash   BYTEA NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX sessions_user_id_idx ON sessions (user_id);
