-- Look up a user by email along with how many passkeys they already have.
SELECT u.id, count(c.id) AS credentials
  FROM users u
  LEFT JOIN webauthn_credentials c ON c.user_id = u.id
 WHERE u.email = $1
 GROUP BY u.id;
