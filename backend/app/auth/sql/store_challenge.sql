-- Persist a ceremony challenge (user_id set for registration, NULL for login).
INSERT INTO webauthn_challenges (challenge, user_id, expires_at)
VALUES ($1, $2, $3)
RETURNING id;
