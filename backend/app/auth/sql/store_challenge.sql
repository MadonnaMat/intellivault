-- Persist a ceremony challenge. user_id is set for an add-passkey ceremony;
-- email/display_name for a registration; all NULL for a login.
INSERT INTO webauthn_challenges (challenge, user_id, email, display_name, expires_at)
VALUES ($1, $2, $3, $4, $5)
RETURNING id;
