# Pimify — Pure PIM Pivot TODO

> Single source of truth for Human + Agent. Django monolith, SQLite/WAL now, Postgres-ready later.
> Stack target: **Python 3.14 + uv 0.9.16 + Django 6.1.1 + Unfold 0.107 + Ninja 1.7.1**. No ES/Celery/DAM until Phase 3+.

## Legend
- `[ ]` todo, `[x]` done, `[~]` in-progress / deprecated-but-live
- Phases must stay green/runnable after each step. `dbbackup` before every migration phase.

---

## Phase 0 — Stack Modernization (MVP enabler) — DONE 2026-10-02, uncommitted

Goal: pip -> uv, Py 3.14, Django 6.1, proper .env, Docker green.
Resolved: Django 6.1.1, Unfold 0.107.0, Ninja 1.7.1, money 3.6.1, import-export 4.4.1.

- [x] Add `pyproject.toml` (requires-python>=3.14, Django==6.1.1, Ninja==1.7.1, Unfold==0.107.0) + `.python-version` (=3.14) + `uv.lock` (kept `requirements.txt` as fallback)
- [x] Verify: `uv sync --locked && check && test` green (0 tests, 0 issues)
- [x] Add `.env.example` + local `.env` (gitignored); `manage.py MODE` and `OPEN_EXCHANGE_RATES_APP_ID` resilient with defaults
- [x] Fix boot blockers:
  - [x] `core/wsgi.py`: `core.settings` (invalid empty pkg) -> `core.settings.{MODE}`
  - [x] `STORAGES` moved to base (prod keeps manifest override); removed double WhiteNoise insert
  - [x] `production.py`: `DOMAIN` full-origin + hostname derived for `ALLOWED_HOSTS`; `CSRF_TRUSTED_ORIGINS` with scheme; `DEBUG` forced False
  - [x] `base.py`: merged duplicate `OPTIONS.init_command` (second key silently overwrote WAL)
  - [x] `.gitignore`: added `.venv`, un-ignored `api/migrations` (see below)
- [x] FIX found during Phase 0: `api/` had **zero migrations** — tables never created on fresh envs; deploy-time `makemigrations api` papered over it. Generated + committed `api/migrations/0001_initial.py` (Django 6.1.1). Scripts run `migrate --fake-initial`: pre-uv installs (tables exist, no recorded migration) get FAKED with zero data touch — proven on a faithful legacy-DB reproduction (row survives, `[X]` recorded); fresh DBs migrate normally. Scripts never generate migrations at runtime; dev `install.sh/.bat` fail loudly via `makemigrations --check` guard
- [x] FIX (audit): `TODO.md` was gitignored — removed, it is the shared source of truth and must be committed
- [x] FIX (audit): `api/migrations/__pycache__/*.pyc` would have been committed — ignored in `.gitignore` + `.dockerignore`, stray files deleted
- [x] FIX (audit): dead `[build-system]`/hatch config removed from `pyproject.toml` (`package = false` never builds); dropped no-op `--no-install-project` from Dockerfile
- [x] FIX (audit, pre-existing bug): `scheduler.py` called `call_command` with no import — added; verified importable
- [x] FIX (audit): `.env.example` advertised `DEBUG`/`LOG_LEVEL` (never read by any settings module — confirmed by grep) — removed; wired `DBBACKUP_CLEANUP_KEEP[_MEDIA]` via `config(..., default=3)` so the example values are real
- [x] `.dockerignore`: removed `api/migrations` + `README.md` (Dockerfile COPY needs it), added `.venv/.git`
- [x] Rewrite scripts to uv: `install.sh / install.oci.sh / install.bat` (`uv sync --locked`, correct migrate order, scheduler NOT auto-started — it blocks; run separately)
- [x] `Dockerfile`: `python:3.14-alpine` + uv binary layer + cached `uv sync` + non-root `appuser`
- [x] Local smoke green: `check` 0 issues, `migrate` OK, `makemigrations --check` clean, `collectstatic` 170 files, `check --deploy` 2 expected warnings (SSL redirect off by design, dummy key), runserver `/health` 200, `/` 301, `/dashboard/` 302, `/products/` 401-not-500 (tables exist, auth works)
- [ ] REMAINING: `docker build -t pimify:uv .` needs first-time base pulls (python:3.14-alpine + uv image) — timed out at 5min in this env. Run on fast network, then `docker run --env-file .env -p 8000:8000 pimify:uv`

---

## Phase 1 — Strip to Pure PIM (MVP)

Goal: remove WMS/Procurement/pricing-engine from `api/`, deprecate safely.

### 1.1 Deprecate (don't delete yet) — DONE 2026-10-02, uncommitted
- [x] `api/middleware.py:DeprecationMiddleware` adds `Deprecation: true + Sunset: Thu, 01 Apr 2027` to: `private/suppliers*, private/warehouses*, private/stocks*, private/product-supplier*, public/exchange-rate*, public/convert-product-price*`. Verified live: deprecated paths carry headers on 200/401/404; healthy paths (`/health`, `/products/`) carry none
- [x] Dashboard KPIs (`api/views.dashboard_callback`): `Total Stock Value` + `Low Stock Alert` replaced with `Total Products / Catalog Completeness (Phase 2 stub) / Missing Media`. Verified by direct call
- [x] `SIDEBAR: Stock Management` in `core/settings/base.py:UNFOLD` commented out (models/admin untouched). Dashboard still 302s correctly

### 1.2 Extract apps (copy, not move — shared db_table for 1 release) — DONE 2026-10-02, uncommitted
- [x] `catalog` (empty placeholder — models land in Phase 2), `inventory`, `procurement` created, all in `LOCAL_APPS`
- [x] `inventory/`: unmanaged `Warehouse` + `Stock` mirrors (`managed=False`, same `db_table`); FKs use `DO_NOTHING + related_name='+'`. `procurement/`: unmanaged `Supplier` + `ProductSupplier` mirrors, same pattern
- [x] CORRECTION to plan: unmanaged mirrors DO generate `0001_initial.py` (state tracking) — but Django strips relation fields and emits zero DDL for them by design (proven in 6.1 source + fresh-DB test: api.0001 creates tables, mirror 0001s apply as no-ops). `makemigrations --check` stays clean
- [x] Old `api/models.py` stays canonical: `Stock.save()` override removed, replaced by `inventory/signals.py:update_product_stock_cache` (post_save, byte-identical behavior incl. updated_at bump). Parity proven by 3 new `inventory/tests.py` tests (create / multi-row sum / update-recompute) — first tests in repo, all pass
- [x] Old `requirements.txt`-era note: mirrors deliberately NOT registered in admin (would duplicate api admin)
- [x] FIX (audit 2026-10-02): mirrors enforced read-only — instance save/delete, manager create/get_or_create/update_or_create/bulk_create, and queryset update/delete all raise NotImplementedError naming the canonical api model (signal binds api.Stock only; silent divergence proven before fix). Covered by MirrorReadOnlyTest in both apps (16 tests total, all pass)
- [x] FIX (audit 2026-10-02): post_delete receiver recomputes stock_quantity (old override never handled deletes → stale totals proven: 5 stayed 5); cascade product-delete guarded via product_id lookup + None check (proven: no crash, rows gone). Delete-to-zero covered by tests

### 1.3 Decouple writes
- [ ] Move `Stock.save()` aggregate to `inventory/signals.py:update_product_stock_cache` -> transitional `Product.stock_quantity_cached`
- [ ] Change `Product.stock_quantity` to read-only `@property` in serializers/admin (stop direct writes)
- [ ] Freeze price: add `catalog.Product.list_price = MoneyField` (copy from `price`), dual-write in `save()`, `RunPython` backfill `price,price_currency -> list_price,list_price_currency`
- [ ] Remove `convert_money` usage; keep raw amount. Remove `djmoney.contrib.exchange` from `INSTALLED_APPS` only after routers removed
- [x] Fix `public_routers.py:list_products`: `search` no longer discards `is_active`/price filters and no longer forces `is_active=True`; `0` price bounds now respected (`is not None`). CORRECTION to plan: `price__gte=<float>` was already correct — amount column IS `price`, no `price_amount` column exists; verified empirically on djmoney 3.6.1 (only the search-reset + falsy-zero parts were real bugs). Live-verified `?search=smoke` returns 200 with correct row

### 1.4 Cutover + Drop
- [ ] Point Ninja public routers to `catalog` querysets; private WMS routers to `inventory/procurement`
- [ ] One green release with both paths live + verified `dbbackup`
- [ ] Delete from `api/models.py`: `stock_quantity` column, `Warehouse/Stock/Supplier/ProductSupplier`, exchange routers/job (`scheduler.sync_exchange_rates`)
- [ ] Delete exchange scheduler job, keep `backup_db/media + delete_old_job_executions`
- [x] Fix `scheduler.py` missing `from django.core.management import call_command` — DONE in Phase 0
- [x] Fix `base.py:DATABASES OPTIONS` duplicate `init_command` key — DONE in Phase 0 (merged; WAL was silently dropped)

---

## Phase 2 — Core PIM (MVP)

Goal: minimal correct PIM domain in `catalog/`.

### 2.1 Models (`catalog/models.py` — SQLite now, PG-ready)
- [ ] `Locale(code PK, name, is_active)` + `Channel(code PK, name, default_locale FK, locales M2M, default_currency)`
- [ ] `Category(id NanoID, name, slug, parent FK-self null, kind: master|collection, sort)` + `ProductCategory(product FK, category FK, is_primary bool)`
  - [ ] Migrate flat `Category(name,slug)` -> add nullable `parent/kind/sort`, backfill `kind=master`
- [ ] `AttributeGroup(code PK, name, sort)` + `Attribute(code PK, label, type: text|textarea|number|boolean|date|url|select|multiselect|json, is_required, is_localizable, is_channel_scoped, is_variant_axis)` + `AttributeOption(id, attribute FK, code, label, sort)` + `AttributeSet/Family(code PK, name, groups M2M, attributes M2M)`
- [ ] `Product(id NanoID PK, sku unique [model code], family FK null, is_active, list_price Money, timestamps)` — NO stock, NO cost
- [ ] `ProductValue(product FK, attribute FK, channel null, locale null, value_text/value_decimal/value_bool/value_date + option FK + options M2M + value_json JSON)` + `UniqueConstraint(product,attribute,channel,locale)` + `clean()` per type/scope
- [ ] `ProductVariant(id NanoID, product FK, sku unique, is_default, sort)` + `VariantValue(same shape, variant FK)` — only axis + variant-scoped attrs
- [ ] `ProductMedia(id, product null, variant null, file, role: main|gallery|swatch|manual, sort, channel null, locale null, alt_text)` — preserve `media/product_images/` paths, keep `post_delete` cleanup
  - [ ] Migrate `ProductImage(productFK)` -> `ProductMedia(role=gallery, sort=0)`
- [ ] `ProductAssociation(from FK, to FK, type: upsell|cross-sell|bundle|accessory)`
- [ ] `History`: add `django-simple-history` (Unfold-native) on `Product/Variant/Value`, not custom table
- [ ] `CompletenessRule(channel FK, locale FK, family FK, required_attrs M2M)` — computed %, denormalized `completeness_cache`, not live aggregate
- [ ] `Brand(name)` lightweight entity OR string on Product (do NOT keep full `Supplier` in catalog)
- [ ] Invert `Organization.api_keys FK` -> `APIKey.organization FK` (data migrate: assign all keys to first org)

### 2.2 API (Ninja, read-first, paginated 20, X-API-Key public / django_auth write)
- [ ] Keep: `GET /public/health`, `/organization` (add missing `auth`), `/products/`, `/products/{id}/`, `/categories/`, `/categories/{id}/products/`
- [ ] Evolve: `/products/{id}/images/` -> `/media/` (role/locale/channel)
- [ ] Add: `GET /families/`, `/families/{code}/`, `/attributes/`, `/attributes/{code}/`, `/products/{id}/variants/`, `/variants/{sku}/`, `/products/{id}/media/`, `/products/{id}/relations/?type=`, `/products/{id}/completeness/?channel=&locale=`, `/channels/`, `/locales/`, `/categories/tree/`
- [ ] Defer `POST/PATCH /products/, /variants/, /values/` until reads stable

### 2.3 Admin (Unfold)
- [ ] `ProductAdmin`: drop `stock_quantity` col; add `VariantInline (sortable,paginated)`, `ValueInline (conditional widget by type)`, `MediaInline (file widget)`, `Category M2M + primary`; fieldset tabs `General|Attributes|Variants|Media|Relations|History`
- [ ] New: `AttributeAdmin (OptionInline)`, `AttributeSetAdmin`, `Channel/LocaleAdmin`, `AssociationAdmin` — all `ImportExportModelAdmin`
- [ ] Sidebar: delete `Stock Management`, add `Catalog (Products,Families,Attributes,Categories,Media)`, `Syndication (Channels,Locales,Completeness)`
- [ ] Dashboard: `Total Products, % Complete (channel/locale), Missing media, Untranslated` + keep recent-actions

---

## Phase 3 — Localization / Channels (Later)

- [ ] Enforce `Value.locale/channel` scoping (only when Channels ship; start product-level + variant-axis only)
- [ ] `Brand` entity hardening if needed
- [ ] Switch SQLite -> Postgres (`JSONB + GinIndex(value_json)`), `DATABASE_URL` in `.env`, zero code change to hybrid values
- [ ] `dbbackup` to S3, `DBBACKUP_CLEANUP_KEEP` review
- [ ] No ES/Celery/DAM yet — `prefetch_related(values,variants)`, `completeness_cache` is enough

---

## Phase 4 — Syndication + Integrations + Product Studio (Later)

- [ ] Export engine first: generic `ChannelFeed (CSV/JSON) + webhook` per `Channel`, not 10 native connectors
- [ ] Native connectors (Amazon, Flipkart, Shopify) one-by-one, outbound only: `PIM -> Commerce (title,attrs,media,list_price)`
- [ ] ERP/WMS inbound read-only: `ERP -> PIM (stock_qty,cost as cache)`. NEVER let PIM own stock again
- [ ] Version diff / publish workflow (`simple-history` compare + `is_published` gate)
- [ ] `catalog/studio/` — ONE custom `Jinja + Datastar` page: variant matrix bulk-edit (Excel-like, auto-save). Keep Unfold for all CRUD (Attributes/Families/Channels/Users/Logs). Rule: single-object=Unfold, 200-cells=Studio

---

## Decisions Locked
- Attribute modeling: **Hybrid single-table typed Value** (typed cols + value_json). NOT pure EAV (5-table ORM hell), NOT pure JSONB (unqueryable on SQLite, no validation).
- PIM owns `list_price/msrp` only. `cost_price/lead_time/stock` are non-PIM.
- `Supplier.name` as `Brand` is PIM; full vendor record is not.
- Monolith stays. No microservices.

## Risks Checklist (check before each release)
- [ ] EAV N+1 guarded? (`prefetch_related`, paginate 20, `completeness_cache`)
- [ ] API break announced? (`410 Gone + Sunset` for dropped paths, 1-release overlap)
- [ ] Backfill reversible? (`RunPython` reverse, `db.sqlite3.bak` verified)
- [ ] Unfold/Ninja/Django compat tested? (`check`, dashboard screenshot, docs 200)
- [ ] Over-scope? (no per-locale/channel explosion before Phase 3, no native connector before generic feed)

---

## Top 5 Next Actions (this week)
1. [ ] Phase 0 files: `pyproject.toml + .python-version + uv.lock + .env.example` (keep requirements.txt), `uv sync --locked && check+test` green
2. [ ] Fix `wsgi.py` + `STORAGES` + `CSRF_TRUSTED_ORIGINS` before Django 6.1 bump
3. [ ] Bump Django/Unfold/Ninja via uv, `migrate + collectstatic`, screenshot dashboard+docs
4. [ ] Rewrite `install.* + Dockerfile` to uv, fix migrate-order bug, `docker build+run` smoke (`/health`, `/organization`)
5. [ ] Deprecate 7 non-PIM endpoints with `Sunset` headers, scaffold empty `catalog/, inventory/, procurement/`
