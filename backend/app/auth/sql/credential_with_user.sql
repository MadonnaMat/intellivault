-- Fetch a passkey and its owner by raw credential id (login assertion lookup).
SELECT c.id, c.public_key, c.sign_count, u.id AS user_id, u.email, u.display_name
  FROM webauthn_credentials c
  JOIN users u ON u.id = c.user_id
 WHERE c.credential_id = $1;
