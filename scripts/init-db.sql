-- Runs on first postgres container init (docker-entrypoint-initdb.d).
CREATE DATABASE app_test;
\c app
CREATE EXTENSION IF NOT EXISTS vector;
-- Better Auth tables live in their own schema, separate from API-owned tables.
CREATE SCHEMA IF NOT EXISTS auth;
\c app_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS auth;
