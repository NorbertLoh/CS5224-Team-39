-- Fresh disposable telelink database only; synthetic local credentials.
CREATE ROLE identity LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO identity;
CREATE SCHEMA identity AUTHORIZATION identity;
