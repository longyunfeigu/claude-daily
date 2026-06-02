# sample_minimal fixture

Hand-built fixture for emit/upload unit tests.

**This is structure coverage, not realistic LLM output.** Real Stage 2
artifacts are richer; this fixture exists to:
- Cover all required schema fields
- Exercise short→full mapping
- Exercise summary derivation (LLM-written, not regex)
- Exercise value_tag normalization

For realistic fixture (post-redact real run), see future Story / smoke_full.sh.
