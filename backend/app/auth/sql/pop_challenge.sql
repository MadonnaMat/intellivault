-- Consume a still-valid ceremony challenge (single use).
DELETE FROM webauthn_challenges
 WHERE id = $1 AND expires_at > now()
RETURNING challenge, user_id;
