-- Update the signed-in user's email and/or display name.
UPDATE users
   SET email = $2, display_name = $3
 WHERE id = $1
RETURNING id, email, display_name;
