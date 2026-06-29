#!/bin/bash
# Initialize PostgreSQL with pgvector extension
# Runs automatically via docker-entrypoint-initdb.d on first volume init.
# The database itself is created by POSTGRES_DB in the compose file.

set -e

echo "Enabling pgvector extension on $POSTGRES_DB..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

echo "✅ Database $POSTGRES_DB ready with pgvector"
