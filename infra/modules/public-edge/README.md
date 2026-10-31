# RF27 public edge

Reusable CloudFront module with private S3 origin access, narrowly scoped public
clinic cache behaviors, uncached API/signalling paths and frontend-only SPA rewriting.
It manages the frontend bucket policy, so W04 must not manage a competing policy.

Inputs and cache semantics: [RF27 guide](../../../docs/RF27-aws-runtime-config.md).
`tests/cache.tftest.hcl` contains synthetic example inputs and mocked plan checks.
