-- Does this passkey belong to this user? (Failure-path disambiguation for a
-- delete that returned nothing: 1 => it was the last one, 0 => not found.)
SELECT count(*) FROM webauthn_credentials WHERE id = $1 AND user_id = $2;
