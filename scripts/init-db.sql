-- Runs on first postgres container init (docker-entrypoint-initdb.d).
CREATE DATABASE app_test;
\c app
CREATE EXTENSION IF NOT EXISTS vector;
\c app_test
CREATE EXTENSION IF NOT EXISTS vector;
