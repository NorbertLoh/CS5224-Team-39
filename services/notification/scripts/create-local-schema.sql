-- Only a fresh disposable telelink database; synthetic credentials.
CREATE ROLE notification LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO notification;
CREATE SCHEMA notification AUTHORIZATION notification;
