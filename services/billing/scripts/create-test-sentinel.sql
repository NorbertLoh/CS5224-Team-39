-- Disposable test database only; run after create-local-schema.sql as administrator.
CREATE SCHEMA b01_sentinel;
CREATE TABLE b01_sentinel.records (marker text NOT NULL);
INSERT INTO b01_sentinel.records VALUES ('untouched');
CREATE TABLE public.b01_sentinel (marker text NOT NULL);
INSERT INTO public.b01_sentinel VALUES ('untouched');
GRANT USAGE ON SCHEMA b01_sentinel TO billing;
GRANT SELECT ON b01_sentinel.records, public.b01_sentinel TO billing;
