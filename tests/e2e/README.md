# Cross-service checks

Reserved for focused integration checks when justified by implementation. I01-I05 and Q01-Q06 define the prototype walkthroughs; manual evidence is acceptable. Broad browser automation is deferred.

- `check_i01_journey.py`: submits the pending I01 clinic and verifies the resulting approved clinic, confirmed appointment and succeeded payment. See [I01 local journey](../../docs/I01-local-journey.md).
- `check_i02_journey.py`: seeds the I02 clinic catalogue and verifies the completed consultation, issued prescription and private PDF download. See [I02 local journey](../../docs/I02-local-journey.md).
