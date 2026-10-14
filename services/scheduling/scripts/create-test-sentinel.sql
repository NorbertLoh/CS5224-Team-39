-- Run as administrator in a disposable test database only, after provisioning.
CREATE TABLE public.s01_sentinel(id integer);
INSERT INTO public.s01_sentinel VALUES (1);
GRANT SELECT ON public.s01_sentinel TO scheduling;
