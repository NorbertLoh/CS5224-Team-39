-- Disposable tests only; run as an administrator after create-local-schema.sql.
CREATE SCHEMA unrelated;
CREATE TABLE unrelated.sentinel(value text NOT NULL);
INSERT INTO unrelated.sentinel VALUES ('preserve');
GRANT USAGE ON SCHEMA unrelated TO clinical_records;
GRANT SELECT ON unrelated.sentinel TO clinical_records;
