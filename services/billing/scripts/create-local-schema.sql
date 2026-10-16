-- Fresh disposable/local database only; run as the PostgreSQL administrator.
CREATE ROLE billing LOGIN PASSWORD 'local-demo-only'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT CONNECT ON DATABASE telelink TO billing;
CREATE SCHEMA billing AUTHORIZATION billing;
-- No other service schema/table privileges are granted.
