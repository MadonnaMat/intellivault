-- All of a user's passkeys, oldest first, for the account page.
SELECT id, name, created_at, last_used_at, transports
  FROM webauthn_credentials
 WHERE user_id = $1
 ORDER BY created_at;
