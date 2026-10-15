-- Disposable verification database only: document must not own other schemas.
CREATE SCHEMA p01_sentinel;
CREATE TABLE public.p01_sentinel (marker text NOT NULL);
INSERT INTO public.p01_sentinel VALUES ('untouched');
GRANT SELECT ON public.p01_sentinel TO document;
