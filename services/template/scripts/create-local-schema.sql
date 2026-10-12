-- Fresh disposable local database only; synthetic credentials, not for AWS.
-- Run as the PostgreSQL administrator before Alembic uses the service role.
CREATE ROLE template LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO template;
CREATE SCHEMA template AUTHORIZATION template;
