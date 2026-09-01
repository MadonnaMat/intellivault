-- Delete one of the user's passkeys, but only while it is not their last one.
-- The subquery guard makes the count-and-delete atomic against concurrent
-- deletes. No row back => either not found or it was the last remaining one;
-- the caller disambiguates.
DELETE FROM webauthn_credentials
 WHERE id = $1
   AND user_id = $2
   AND (SELECT count(*) FROM webauthn_credentials WHERE user_id = $2) > 1
RETURNING id;
