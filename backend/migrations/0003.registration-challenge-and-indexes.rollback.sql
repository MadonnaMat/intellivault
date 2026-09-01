DROP INDEX users_email_lower_key;
DROP INDEX sessions_expires_at_idx;
DROP INDEX webauthn_challenges_expires_at_idx;
ALTER TABLE webauthn_challenges DROP COLUMN display_name;
ALTER TABLE webauthn_challenges DROP COLUMN email;
