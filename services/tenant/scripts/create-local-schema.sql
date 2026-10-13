-- Fresh disposable telelink database only; synthetic local credentials.
CREATE ROLE tenant LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO tenant;
CREATE SCHEMA tenant AUTHORIZATION tenant;
