# bookchaowalit-trading-backend

**Owner:** `bookchaowalit-ai`  
**Default branch:** `master` (historical; prefer `main` for new work)  
**Role:** Backend/services supporting trading automation experiments (bots, logs, migration notes).

## What this is

A nested backend checkout used with the broader trading portfolio (see sibling
`booktrading` product under `bookchaowalit-ai/book-products/`). This tree holds
operational pieces such as `trading-bots/` and migration notes — it is **not**
the full interview UI/product case study.

## Quick layout

| Path | Role |
|---|---|
| `trading-bots/` | Bot code / runtime experiments |
| `NEON_MIGRATION_COMPLETE.md` | DB migration note |
| `logs/` | Local logs (do not commit secrets) |
| `.env.example` under bots (if present) | Template only |

## Auth / secrets

- Use `.env.example` / templates only in Git.
- Never commit live exchange keys, webhook URLs, or DB credentials.
- Prefer read-only / paper modes unless a written kill-switch policy exists
  (see `booktrading` PRODUCT for observe-first philosophy).

## Run (high level)

```bash
# Inspect first — stack varies by bot package
ls trading-bots
# Follow per-bot docs/requirements if present
```

## Tests / quality

This repo may lack a unified test runner. Do **not** claim CI green without
running the specific package tests. Interview claims should point at
`booktrading` (frontend + multi-language suite) unless this tree has its own
passing suite.

## Related

- Interview flagship: `bookchaowalit-ai/booktrading`
- Org transfer to `bookchaowalit-backend` is **deferred** (Book Dev BD-034)
- Catalog: Solo Empire `BOOK-DEV-BACKLOG-BD.md` BD-013
