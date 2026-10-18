-- Local synthetic database only. Run once as an administrator.
CREATE ROLE consultation LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO consultation;
CREATE SCHEMA consultation AUTHORIZATION consultation;
