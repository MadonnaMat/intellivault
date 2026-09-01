import { Client } from "pg";

const AUTH_TABLES = "users, sessions, webauthn_credentials, webauthn_challenges";

/** DSN for the database the running backend uses. The e2e run owns this data. */
const dsn =
  process.env.E2E_DATABASE_URL ??
  "postgresql://intellivault:intellivault@localhost:5432/intellivault";

export async function resetDb(): Promise<void> {
  const client = new Client({ connectionString: dsn });
  await client.connect();
  try {
    await client.query(`TRUNCATE ${AUTH_TABLES} CASCADE`);
  } finally {
    await client.end();
  }
}

/** Insert a bare users row, to simulate a second registration winning a race. */
export async function seedUser(email: string): Promise<void> {
  const client = new Client({ connectionString: dsn });
  await client.connect();
  try {
    await client.query("INSERT INTO users (email, display_name) VALUES ($1, 'seed')", [
      email,
    ]);
  } finally {
    await client.end();
  }
}
