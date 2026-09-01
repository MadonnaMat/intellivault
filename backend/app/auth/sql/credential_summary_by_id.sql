-- The account-page view of a single passkey.
SELECT id, name, created_at, last_used_at, transports
  FROM webauthn_credentials
 WHERE id = $1;
