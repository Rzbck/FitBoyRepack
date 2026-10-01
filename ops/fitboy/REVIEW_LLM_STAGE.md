# Autonomous review LLM stage

This stage runs after the deterministic V2 Wikidata pass and only considers active jobs already in `review`.

Safety and quality rules:

- `done` rows are never requeued or sent to the LLM.
- If V2 still has `pending` or `processing` work, the review service exits immediately so the deterministic stage keeps priority.
- The worker reads only cached Wikidata candidates produced by V2; it performs no second metadata crawl.
- Qwen is allowed to choose only one supplied Wikidata candidate ID or `null`.
- Only complete, game-like candidates with a Wikidata ID, label, evidence URL, release date and genre are eligible for an LLM call.
- The LLM never supplies the stored title/date/genre/developer/publisher/platform facts. On acceptance, those fields are copied from the chosen Wikidata candidate.
- Low-confidence or null decisions remain `review`.
- Rows with no evidence or incomplete evidence remain `review` without consuming an LLM call.
- A versioned `llm_review_state` table prevents repeated timer calls for the same unresolved catalog fingerprint. Errors may be retried up to the configured limit.

The systemd service is bounded to 12 LLM calls per activation and is scheduled every 30 minutes. It can only connect to localhost, where the reusable llama.cpp OpenAI-compatible service listens.

Useful status commands:

```bash
systemctl status review-llm.timer review-llm.service --no-pager
journalctl -u review-llm.service -n 100 --no-pager
journalctl -fu review-llm.service
```

The first-stage V2 timer remains independent and authoritative. If new catalog entries appear, V2 processes them first; the review stage yields until the first-stage queue is clear again.
