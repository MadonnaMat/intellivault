-- Create the account for a just-verified registration. If the email was taken
-- between "begin" and "finish" (a concurrent registration), no row comes back.
INSERT INTO users (email, display_name)
VALUES ($1, $2)
ON CONFLICT (email) DO NOTHING
RETURNING id, email, display_name;
