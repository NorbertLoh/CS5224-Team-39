-- Fresh disposable telelink database only; synthetic local credentials.
-- The administrator owns the shared extension; migrations never remove it.
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;
CREATE ROLE scheduling LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO scheduling;
CREATE SCHEMA scheduling AUTHORIZATION scheduling;
