-- Disposable local database only. Run as administrator before service migrations.
CREATE ROLE fulfilment LOGIN PASSWORD 'local-demo-only';
GRANT CONNECT ON DATABASE telelink TO fulfilment;
CREATE SCHEMA fulfilment AUTHORIZATION fulfilment;
-- No access to clinical-records, identity, or any other service schema is granted.
