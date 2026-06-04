-- Create the test database
CREATE DATABASE selfhost_studio_test;

-- Grant all privileges on both databases
GRANT ALL PRIVILEGES ON DATABASE selfhost_studio TO postgres;
GRANT ALL PRIVILEGES ON DATABASE selfhost_studio_test TO postgres;

-- Enable pgvector extension on default and test databases
CREATE EXTENSION IF NOT EXISTS vector;
\c selfhost_studio_test
CREATE EXTENSION IF NOT EXISTS vector;