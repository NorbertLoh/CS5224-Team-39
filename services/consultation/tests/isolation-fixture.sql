-- Disposable test database only; run as administrator.
CREATE SCHEMA unrelated;
CREATE TABLE unrelated.sentinel(value text NOT NULL);
INSERT INTO unrelated.sentinel VALUES ('preserve');
GRANT USAGE ON SCHEMA unrelated TO consultation;
GRANT SELECT ON unrelated.sentinel TO consultation;
