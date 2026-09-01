-- Validate a session token (by hash), refresh last_seen_at, return the user.
UPDATE sessions AS s
   SET last_seen_at = now()
  FROM users AS u
 WHERE s.user_id = u.id
   AND s.token_hash = $1
   AND s.expires_at > now()
RETURNING u.id, u.email, u.display_name;
