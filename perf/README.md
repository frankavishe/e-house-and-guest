# Search performance (T145, SC-002)

Target: p95 of `GET /api/v1/listings/search` < 500 ms server-side with 20,000 listings.

## Run it

```powershell
docker compose exec -T api uv run --frozen python -m app.seed --all
docker compose exec -T api uv run --frozen python -m app.seed_perf --count 20000
Get-Content perf/search.js | docker run --rm -i -e BASE_URL=http://host.docker.internal:8010 grafana/k6:0.54.0 run -
```

`BASE_URL` is the API as seen from the k6 container. Use your `API_PORT` (8000 by default). `RATE` (requests/s, default 20) and `DURATION` (default 60s) tune the load. The script mixes 12 query shapes:

- category browse
- region and price filters
- text search
- attribute filters
- each booking mode's period (nights, days, slots, months, stock quantity)
- the four sort orders
- pages 1–3

## Results (2026-10-22, dev laptop, Docker Desktop, one `uvicorn --reload` process)

20,085 listings in the database; one third of non-stock listings carry an owner block.

| Run | Rate | p50 | p90 | p95 | Max | Errors |
|---|---|---|---|---|---|---|
| Baseline | 20/s | 91 ms | 871 ms | **1.10 s** ✗ | 2.31 s | 0 % |
| After fixes | 20/s | 41 ms | 71 ms | **101 ms** ✓ | 323 ms | 0 % |
| After fixes, stress | 50/s | 593 ms | 3.0 s | 4.1 s | 10.8 s | 0 % (dropped 449 iterations) |

At 20/s the target holds with a wide margin. A single dev process saturates at about 40 requests/s. Each search costs about 20 ms of DB time (count + page) and about 20 ms of Python. The ceiling is per process, so production should run `uvicorn --workers N` (or several containers) sized to traffic; see docs/operations.md.

## What was wrong

1. **Stock availability subquery was not correlated (correctness bug, and slow).**
   - In search, `stock_shortfall` sits two levels below the outer query: `EXISTS (SELECT day FROM generate_series … WHERE (SELECT sum(...)))`. SQLAlchemy's auto-correlation only looks one level up, so `listings` was added to the inner `FROM`, giving `FROM availability_blocks, listings`.
   - The sum then counted every listing's stock blocks. A tent listing could disappear from search because a different listing was booked.
   - Fixed with `.correlate_except(b)` in `backend/app/availability/service.py`. A regression assertion is in `tests/integration/test_search.py::test_stock_availability`.
   - Before: about 430 ms per tents search. After: about 45 ms.
2. **The partial GiST index on blocks was never used.**
   - `ix_availability_blocks_listing_period` is `WHERE active`, but queries said `active IS TRUE`. Postgres cannot prove that matches the index predicate.
   - Every availability check (search, booking, calendars) therefore seq-scanned `availability_blocks` once per listing-day: 1,799 loops in the plan above.
   - Queries now use the bare `active` column.

No new indexes were needed. The existing ones cover everything once the predicate matches:

- partial `(status, category_id, district_id)`
- GIN `jsonb_path_ops` on attributes
- GIN on `search_tsv`
- `base_price_tzs`
- `(lat, lng)`

## Checking plans

To see the slowest statements during a run:

```sql
ALTER SYSTEM SET log_min_duration_statement = 150; SELECT pg_reload_conf();
-- run k6, then: docker compose logs db | Select-String duration
ALTER SYSTEM RESET log_min_duration_statement; SELECT pg_reload_conf();
```
