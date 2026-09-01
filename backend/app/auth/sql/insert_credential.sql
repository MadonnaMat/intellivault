-- Store a freshly verified passkey for a user.
INSERT INTO webauthn_credentials
    (user_id, credential_id, public_key, sign_count, transports, aaguid, name)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING id;
