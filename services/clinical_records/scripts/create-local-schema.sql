-- Run once as an administrator against a synthetic local database.
CREATE ROLE clinical_records LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO clinical_records;
CREATE SCHEMA clinical_records AUTHORIZATION clinical_records;
