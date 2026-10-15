-- Fresh disposable telelink database only; synthetic local credentials.
CREATE ROLE document LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO document;
CREATE SCHEMA document AUTHORIZATION document;
