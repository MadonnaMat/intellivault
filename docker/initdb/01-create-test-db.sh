#!/bin/sh
# Runs once, the first time the postgres volume initializes. Creates a
# dedicated <POSTGRES_DB>_test database so test runs never share state
# with the real application database.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	CREATE DATABASE ${POSTGRES_DB}_test OWNER ${POSTGRES_USER};
SQL
