# Wikidata rate-limit handling

The bulk metadata worker uses Wikimedia's public Action API conservatively:

- no local LLM calls during the first pass;
- at most 3 worker threads, with a global request interval;
- `maxlag=5` on Action API requests;
- `Retry-After` is honored for HTTP 429/503 responses;
- exponential backoff is used when `Retry-After` is absent;
- transient rate-limit/service errors are requeued as `pending`, not recorded as permanent failures;
- successful evidence is cached in the local SQLite sidecar.

The default request interval is intentionally conservative for an unauthenticated VPS client and can be tuned after a real benchmark.
