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
- [x] Stock aggregate lives in `inventory/signals.py` (post_save + post_delete); transitional `stock_quantity_cached` deemed unnecessary — the signal already owns the single write path and `stock_quantity` dies with the api model drop below. Original item superseded
- [ ] Change `Product.stock_quantity` to read-only `@property` — DEFERRED to model-drop cleanup (property + column can't coexist; the column goes with the api model)
- [x] SUPERSEDED by 2.1 backfill: `catalog.Product.list_price` copied from `api.price` once (no dual-write needed); `api.price` stays untouched until the 1.4 drop. Original item: ~~Freeze price: add `catalog.Product.list_price = MoneyField` (copy from `price`), dual-write in `save()`, `RunPython` backfill~~
- [x] Exchange removed, not just deprecated: endpoints deleted (404; Sunset headers still attach via middleware prefix match), `convert_money`/`Rate` gone, `djmoney.contrib.exchange` removed from INSTALLED_APPS (tables dropped via `migrate exchange zero` first), `DJANGO_MONEY_RATES` + `OPEN_EXCHANGE_RATES_APP_ID` setting + `.env` keys deleted, scheduler job + initial sync deleted, dead schemas + stale urls.py block cleaned
- [x] Fix `public_routers.py:list_products`: `search` no longer discards `is_active`/price filters and no longer forces `is_active=True`; `0` price bounds now respected (`is not None`). CORRECTION to plan: `price__gte=<float>` was already correct — amount column IS `price`, no `price_amount` column exists; verified empirically on djmoney 3.6.1 (only the search-reset + falsy-zero parts were real bugs). Live-verified `?search=smoke` returns 200 with correct row

### 1.4 Cutover + Drop — DONE 2026-10-05, uncommitted (routers + exchange + org + model drop; green-release ship = next)
- [x] Pre-migration `dbbackup --clean` succeeded (966KB). FIX found en route: dbbackup 5.x hard-fails on legacy `DBBACKUP_STORAGE[_OPTIONS]` settings — moved to `STORAGES["dbbackup"]` alias in base + production (this also un-breaks the scheduler backup jobs, which were silently failing)
- [x] Public routers serve catalog: products list (same query params incl. price bounds, now on `list_price`; +sku in search), detail (no `stock_quantity`), images → media feed (incl. variant rows), categories (catalog, ordered) — legacy api product/category models unread by these paths. Live-verified SMOKE-001 with brand/family fields
- [x] Private routers serve read-only mirrors (`inventory`/`procurement` imports); schemas resolve unchanged (same columns). HTTP-verified via staff session: all four lists 200 with real rows
- [x] `catalog` filter gained `min_price`/`max_price` for `/public/` parity (same verified djmoney amount semantics)
- [x] Catalog `_or_404` promoted to public `or_404`, shared by cutover endpoints (uniform `{"error"}` envelope). Gotcha respected: paginated `categories/{id}/products` keeps bare get_object_or_404 + no declared 404 (proven Phase 2.2: @paginate cannot return non-200)
- [x] Pre-migration `dbbackup --clean` succeeded (966KB). FIX found en route: dbbackup 5.x hard-fails on legacy `DBBACKUP_STORAGE[_OPTIONS]` settings — moved to `STORAGES["dbbackup"]` alias in base + production (this also un-breaks the scheduler backup jobs, which were silently failing)
- [x] `migrate exchange zero` before app removal (no orphan tables); `migrate` clean after; `makemigrations --check` clean
- [x] Dropped `Warehouse/Stock/Supplier/ProductSupplier` (+ `stock_quantity` column) from `api/models.py` via option (a): `api.0003` wraps the four DeleteModels in SeparateDatabaseAndState (empty database_operations — tables + data intact, verified identical row counts), `stock_quantity` dropped for real (orphaned: nothing read/wrote it). Mirrors keep reading; legacy Product/Category/ProductImage admins made view-only (LegacyReadOnlyMixin: no add/delete, all fields readonly) so no silent API divergence
- [x] With the drop: deleted `inventory/signals.py` (aggregate has no writer; ImportError risk eliminated), removed 4 WMS admins + dead schemas (`ProductInfoSchema`, `ProductImageSchema`), dropped dead exchange middleware prefixes, deleted unused `Field`/`datetime` imports. Retirement guard test fails if the models ever return
- [x] Tests rewritten for the post-retirement world (raw-SQL table seeding — no managed writer exists by design): 63/63 green (removed 6 signal tests for deleted behavior, added retirement + table-survival proofs)
- [ ] Green-release gate: this change IS the dual-path release (legacy + catalog paths live, backup verified). Ship it before any further drops
- [x] Fix `scheduler.py` missing `from django.core.management import call_command` — DONE in Phase 0
- [x] Fix `base.py:DATABASES OPTIONS` duplicate `init_command` key — DONE in Phase 0 (merged; WAL was silently dropped)

---

## Phase 2 — Core PIM (MVP)

Goal: minimal correct PIM domain in `catalog/`.

### 2.1 Models (`catalog/models.py` — SQLite now, PG-ready) — DONE 2026-10-02, uncommitted
- [x] `Locale(code PK, name, is_active)` + `Channel(code PK, name, default_locale FK null, locales M2M, default_currency USD)`
- [x] `Category(id NanoID preserved, name, slug, parent FK-self null + cycle guard in clean(), kind master|collection default master, sort)` + `ProductCategory(product FK, category FK, is_primary, uniq(product,category))`
- [x] `AttributeGroup(code PK, name, sort)` + `Attribute(code PK, label, type×9, group FK null [completion of spec: drives admin fieldsets], is_required/localizable/channel_scoped/variant_axis, sort)` + `AttributeOption(attr FK, code, label, sort, uniq(attr,code))` + `AttributeSet(code PK, name, groups M2M, attributes M2M)`
- [x] `Product(id NanoID preserved, sku unique, name, description, family FK null SET_NULL, brand FK null SET_NULL, list_price Money, is_active, categories M2M via ProductCategory, completeness_cache JSON default dict, timestamps, history)`
- [x] `ProductValue` / `VariantValue`: hybrid typed columns + `value_json`, `option FK + options M2M`, `UniqueConstraint(owner,attribute,channel,locale)`, strict `clean()`: type↔column mapping, exactly-one-representation, option/options attribute-match, locale/channel gating, axis placement (axis⇄variant only), NULL-safe duplicate guard. `is_required` intentionally NOT in clean (family/channel context → completeness engine). MULTISELECT non-empty enforced at form level (needs pk)
- [x] `ProductVariant(id NanoID, product FK CASCADE, sku unique, is_default, sort)` + partial `UniqueConstraint(product where is_default)` — single default enforced at DB level, proven by test
- [x] `ProductMedia(product/variant FK null CASCADE, file→same product_images/ dir, role, sort, channel/locale PROTECT, alt_text, owner-required clean, post_delete file cleanup)` + backfill `ProductImage -> role=gallery, sort=0, PKs preserved`
- [x] `ProductAssociation(from/to FK, type×4, uniq(from,to,type), self-ref guard)`
- [x] `History`: `django-simple-history==3.13.0` added via uv (`simple_history` in INSTALLED_APPS); `HistoricalRecords()` on Product/Variant/ProductValue/VariantValue → 4 history tables, verified on disk
- [x] `CompletenessRule(channel/locale/family FK CASCADE, required_attributes M2M, uniq(channel,locale,family))`
- [x] `Brand(id NanoID, name unique)` entity (no vendor terms)
- [x] Backfill `catalog/backfill.py` (testable fns) + `0002_backfill_from_api` (deps catalog.0001 + api.0001, reversible best-effort): 3/3 products, 0/0 cats/images match; sku/amount/currency/PKs/timestamps preserved; idempotent (update_or_create/get_or_create); 14 catalog tests pass, 30/30 suite green (34/34 after audit fixes)
- [x] FIX (audit 2026-10-02): single primary category per product — partial `UniqueConstraint(product where is_primary)` (`uniq_primary_category_per_product`); second primary now raises IntegrityError, proven by test
- [x] FIX (audit 2026-10-02): single global main + single main per channel, separately for product- and variant-owned media (4 partial uniques; NULL scoping deliberate: variant rows invisible to product constraints and vice versa). Decision recorded: per-channel mains allowed, duplicates within a scope are not
- [x] FIX (audit 2026-10-02): saved-but-empty MULTISELECT now fails `full_clean()` (creation-time still unchecked — M2M needs a pk; completeness engine must also treat empty as unset, see 2.2)
- [x] Cleanup: audit probe rows removed from dev DB (AUD*/AUDIT-* products, c1/c2, reference rows + history orphans); SMOKE-001 fixture kept. Lesson re-proven: new uniqueness migrations fail on violating rows — resolve data BEFORE migrate, not after
- [x] Org/APIKey inversion DONE 2026-10-05 with cutover: `APIKey.organization FK null SET_NULL related api_keys`; `Organization.api_keys` removed; migration `api.0002` applied, all keys intact (NULL org); admins updated (key shows org, org shows key count); tested both directions + loose-key auth

### 2.2 API (Ninja, read-first, paginated 20, X-API-Key public / django_auth write) — DONE 2026-10-02, uncommitted
- [x] New `catalog/` router (`catalog/routers.py` + `catalog/schemas.py`, mounted in `api/main.py`): legacy `/public/` + `/private/` untouched until 1.4 cutover. Shared `api/auth.py:header_key` (extracted from public_routers, no behavior change)
- [x] Keep (+1 security fix): `/organization` now requires `auth=header_key` (was open)
- [x] Evolve: `GET /catalog/products/{id}/media/` (product + variant rows, variant sku set) supersedes legacy `/images/`; old path untouched until cutover
- [x] Added (14 paths live, verified in OpenAPI schema): `families/`, `families/{code}/`, `attributes/`, `attributes/{code}/` (options nested), `products/` (search/active/family filters) + `products/{id}/` (categories w/ is_primary, values resolved, variants+values, product media; NO stock_quantity), `products/{id}/variants/`, `variants/{sku}/`, `products/{id}/media/`, `products/{id}/relations/?type=`, `products/{id}/completeness/?channel=&locale=`, `channels/`, `locales/`, `categories/tree/` (recursive, kind filter)
- [x] Completeness engine: exact-scope OR global value match; empty MULTISELECT counts as unset (2.1 audit decision); 404 when no family/rule; writes `completeness_cache[channel]` via queryset.update (no history row, no updated_at bump) — first and only writer
- [x] Error contract: all 404s return `{"error"}` matching declared schemas (bare get_object_or_404 renders `{"detail"}`, contradicting docs). Gotcha found by test: `@paginate` cannot return non-200 statuses in Ninja 1.7.1 (it paginates the error payload — plain tuples validate as 200, `Status` crashes with KeyError) → variants/media/relations lists are deliberately unpaginated (small per-product collections) with 404 declared
- [x] Variant-less legacy products: exposed truthfully (empty variants array, no synthesis) — implicit-variant decision deferred to cutover
- [x] 17 API tests (TestClient: auth, shapes, filters, math, tree, envelope, schema build); 51/51 suite green (55/55 after audit fixes); live smoke (tree, envelope, staff-only openapi redirect unchanged)
- [x] FIX (audit 2026-10-02): deactivated API keys now rejected — `authenticate()` matches `is_active=True` (was: any stored key worked forever). Test: dead key → 401 on catalog + legacy paths
- [x] FIX (audit 2026-10-02): cross-kind parenting forbidden in `Category.clean()` (master/collection trees must not interleave); `?kind=bogus` and `?type=bogus` now 400 `{"error"}` instead of silent `200 []`. Note: `slug` stays globally unique, so no extra `(parent, slug)` constraint needed. Mixed-kind rows can still only appear via `objects.create` bypass (no clean) — tree builder filters by kind, so they stay invisible rather than corrupt output
- [x] Cleanup: unused `CategorySchema` import dropped from `catalog/routers.py`
- DECISION (Gap 3): `completeness_cache` is advisory, endpoint is authoritative — values writes do NOT invalidate the cache; it refreshes only on `GET .../completeness/`. Revisit with signals if any consumer reads the column directly
- DECISION (Gap 4): unpaginated lists stay unbounded for MVP (per-product collections are small); revisit with a cap if a product ever exceeds ~500 variants/media/relations
- [ ] Defer `POST/PATCH /products/, /variants/, /values/` until reads stable

### 2.3 Admin (Unfold) — DONE 2026-10-02, uncommitted
- [x] `catalog/admin.py`: 13 ModelAdmins (all ImportExport; Product + Variant with SimpleHistoryAdmin mixin — history views render, MRO proven by test). Product change form: Category/Value/Variant/Media inlines with `tab=True`; variants + values `per_page=10`; variant `show_change_link`; ValueInline uses per-row-type form (widget/date-picker/textarea + option queryset scoped to the row's attribute; model clean() still the enforcer); media uses ImageUploaderWidget; deterministic inline ordering via get_queryset (fixes Unfold UnorderedObjectListWarning)
- [x] Reference admins: Attribute (+Option inline) / Family / Channel+Locale / Category / Media / Association / CompletenessRule (+filter_horizontal M2Ms), Brand, Group — list/display/search/filters throughout
- [x] Sidebar: dead Stock-Management comment deleted; new Catalog (Products, Families, Attributes, Categories, Media) + Syndication (Channels, Locales, Completeness) sections; legacy section relabeled "Legacy (deprecated)" so api.* links can't masquerade as catalog (audit fix; section stays reachable until 1.4 cutover)
- [x] `api ProductAdmin`: `stock_quantity` dropped from list_display (display-only)
- [x] Dashboard (`api/views.dashboard_callback` now catalog-driven): Total Products / Catalog Completeness (mean of cached channel scores; "—" until first endpoint score) / Missing Media (counts variant-only media too — audit fix; old `media__isnull` query silently misclassified swatch-only products) / Untranslated (zero localized values; "—" until locales + localizable attrs exist); category distribution from catalog; template grid `lg:w-1/3` → `lg:w-1/4` for 4 cards; recent-actions untouched; dead `json`/`timedelta` imports + unused date-range block removed
- [x] `catalog/test_admin.py`: 5 smoke tests (14 changelists incl. dashboard + legacy api product, add/change forms with all inlines, both history views, sidebar legacy label, Missing Media variant-only regression) — 60/60 suite green. Notable: `force_login`/`client.login` both break dj-login-history's post_login signal (no HTTP_USER_AGENT) → tests use real form POST login. Dead `FieldTextFilter` import dropped from `catalog/admin.py`

---

## Phase 3 — Localization / Channels (Later) — STARTED 2026-10-05 (scoping only; PG deferred per user decision, Litestream deferred, dbbackup stays)

- [x] Scoped resolution, single source of truth: `catalog/resolution.py:resolve_scoped_value` (exact -> channel-only -> locale-only -> global; channel wins ties; empty MULTISELECT never wins). Completeness engine refactored onto it (behavior identical, existing math tests pass unchanged)
- [x] Membership invariant in `BaseAttributeValue.clean()`: channel+locale both set requires locale ∈ channel.locales; either side alone (or neither) always allowed. Rules (`CompletenessRule`) deliberately NOT gated (config chicken-and-egg)
- [x] Scoped reads: `GET /products/{id}/values/?channel=&locale=` (one winning row per attribute, both params optional); `GET .../media/` gained optional `?channel=&locale=` in-scope filters (global rows always included)
- [x] `Brand.slug` (unique, auto-filled from name): stable key for future feeds. No backfill needed (empty table). BrandAdmin lists/searches slug. Review fix: `allow_unicode=True` + never-empty nanoid fallback + `-2` disambiguation (non-Latin names no longer collide on `''`; renames never thrash the slug); `catalog/migrations/0005_alter_brand_slug.py`
- [x] 16 new tests (membership 3, slug 3, resolver 6, endpoints 4); 79/79 suite green
- [ ] `Brand` entity hardening if needed (logo/description deferred — no consumer yet)
- [ ] Postgres: DEFERRED indefinitely — SQLite by design (user decision 2026-10-05; Litestream evaluated and likewise deferred, django-dbbackup stays). Revisit only on measured SQLite limits. `DATABASE_URL` stays commented
- [x] `dbbackup` to S3 (env-gated, default unchanged): `django-storages==1.14.6 + boto3` added; shared `_dbbackup_storage()` helper (base + production) selects S3 when `DBBACKUP_S3_BUCKET` set (bucket/endpoint/region/prefix from env, creds from AWS env chain — never settings); `.env.example` documents contract. Verified: default resolves filesystem, S3 branch instantiates with correct bucket/endpoint/prefix (no network touched; live-bucket upload is a user-side check). `DBBACKUP_CLEANUP_KEEP=3` retained on review (monthly jobs → 3 months of history)
- [ ] No ES/Celery/DAM yet — `prefetch_related(values,variants)`, `completeness_cache` is enough

---

## Phase 4 — Syndication + Integrations + Product Studio (Later)

### 4.0 Generic outbound feed (STARTED 2026-10-05, uncommitted) — PIM→commerce pull model
- [x] `Feed` (name unique, channel+locale FK PROTECT, format json/csv, is_active, only_complete) + `FeedRun` (append-only: status/items/skipped/file/error); migrations 0006 + 0007; FeedAdmin + read-only FeedRunAdmin
- [x] `catalog/feeds.py`: resolved payload (product attrs via shared resolver, per-variant axis values, in-scope media with both params always set, completeness block or null when no rule, `only_complete` + `is_active` filtering); price/currency/description included (name/desc/price are global columns — scope applies to attributes+media); deterministic ordering (sku/code/sort+pk); JSON + CSV (one row per variant) renderers
- [x] Review fixes: completeness counts variant values (engine + feed — variant-axis attrs can reach 100%; `test_api` updated); `only_complete` exclusions recorded in `FeedRun.skipped` (+ command output); rules prefetched once + media prefetched (no per-product queries); CSV cells raw strings (no JSON double-encode); download uses `FeedRunStatus` enum; `GET /feeds/` discovery endpoint; hermetic `tempfile` FEEDS_ROOT in tests
- [x] `build_feed <name|id>` management command → `FEEDS_ROOT` (`BASE_DIR/../feeds`, gitignored); failed builds log a failed run and exit non-zero; inactive/unknown feeds refused
- [x] Runs API: `GET /feeds/` + `GET /feeds/runs/` (paginated, filters) + `GET /feeds/runs/{id}/download/` (basename-guarded FileResponse; 404 envelope for failed/missing)
- [x] 20 new tests; 102/102 suite green
- [x] Scope-semantics decision locked + documented: `/values/` is strict (omitted axis = global-only), `/media/` is a lenient listing (omitted axis = no filter); feed path always passes both, so they agree
- [x] Resolver tiebreak made pk-type agnostic (explicit two-stage compare; no pk negation)
- [ ] Feed scheduling (per-feed cadence via cron calling `build_feed`; scheduler wiring deferred)
- [x] 4.1 publish gate + scheduling: `Product.is_published` (default False) + `published_at` (frozen first-ship; Studio diff baseline) + `last_shipped_at` (every ship); builder ships `is_active AND is_published` only; `FeedRun.skipped` is `{unpublished|incomplete|no_rule: [skus]}` (migration 0008 incl. RunPython converting legacy list rows); `Feed.schedule_cron` (blank = manual, validated at clean); `run_feed()` shared by `build_feed` and scheduler (one job per scheduled feed, `feed_<id>`); `GET /products/{id}/history/` audit endpoint (diff deferred to Studio); admin publish/unpublish actions (per-object saves → history rows). Cron alternative: system cron calling `build_feed` per feed for deployments skipping the scheduler process
- [x] 4.1 review fixes: legacy list-skipped data migration; scheduler skips invalid-cron rows with a warning (one bad row can't kill backups) + purges stale `feed_*` jobs; stamps move to after the file write (failed builds stamp nothing); bulk publish via save() so history records it; history schema gains published_at/last_shipped_at; is_published exposed on product list/detail schemas
- [x] 4.1 tests: 118/118 suite green
- [ ] Platform mappings (Amazon/Flipkart/Shopify attribute profiles on top of the generic payload)
- [x] 4.2 Shopify profile, file-artifact v1: `ProductVariant.list_price` nullable MSRP override (fallback to product price; never cost); `PlatformProfile` (platform/channel unique, attribute_map validated against Attribute codes, category_map, defaults) + `Feed.profile` (PROTECT; migration 0009); `catalog/platforms/` pure transformers (no network) — `productCreate` (title/descriptionHtml/vendor/productType/handle/DRAFT/tags/options/metafields w/ type inference) + `variantsBulkCreate` (price decimal, optionValues, inventoryItem{sku,tracked:false}); option derivation capped at 3, per-SKU skip report (too_many_options/missing_price/no_title), absolute-URLs-only media with warnings; `run_feed` writes `{id}_{stamp}.shopify.json` as the run file when profiled; `Feed.clean` rejects csv+profile; `GET /profiles/`; generic payload gains brand_name + variant price (JSON+CSV); 20 new tests; 155/155 green. Explicitly NOT in slice: push/OAuth, inventoryQuantities (stock never PIM-owned), Shopify category taxonomy IDs, initial-variant reconciliation at push time
- [x] 4.2 review fixes: MULTISELECT axis dedupes by content (was TypeError aborting the build); money always 2dp; metafield types from schema type (DATE/NUMBER correct, artifact strict-json clean); `handle` emitted; platform skips merged into `FeedRun.skipped` + `FeedRun.report` JSON field (migration 0010); 160/160 green
- [ ] Live-bucket/off-site delivery (fetch from runs endpoint; push destinations later if needed)

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

## Risks Checklist (check before each release)- [ ] EAV N+1 guarded? (`prefetch_related`, paginate 20, `completeness_cache`)
- [ ] API break announced? (`410 Gone + Sunset` for dropped paths, 1-release overlap)
- [ ] Backfill reversible? (`RunPython` reverse, `db.sqlite3.bak` verified)
- [ ] Unfold/Ninja/Django compat tested? (`check`, dashboard screenshot, docs 200)
- [ ] Over-scope? (no per-locale/channel explosion before Phase 3, no native connector before generic feed)
- [ ] Custom middleware streaming-safe? (BrotliMiddleware 500'd all static/FileResponse until it skipped streaming — core/tests/test_middleware.py guards it)
- [ ] Unfold `COLORS` values are COMPLETE CSS colors, not Tailwind v3 triplets? (Unfold emits them verbatim into `--color-*` and v4 consumes them unwrapped — `"75 85 99"` shipped as an invalid color and every themed utility silently fell back; core/tests/test_unfold_settings.py guards it). Never load a second Tailwind build alongside Unfold's v4 output.
- [ ] Custom admin templates only use classes Unfold actually ships? (Unfold ships ~400 `dark:` utilities but all on `base-*`/`font-*`/`primary-*` tokens — **never the Tailwind `gray-*` ramp**; a hand-rolled template that used `gray-*` went silently unstyled when the stale v3 stylesheet was removed. core/tests/test_admin_template_css.py parses every `class="…"` and fails on unknown classes.)

---

## Top 5 Next Actions (this week)
1. [ ] Phase 0 files: `pyproject.toml + .python-version + uv.lock + .env.example` (keep requirements.txt), `uv sync --locked && check+test` green
2. [ ] Fix `wsgi.py` + `STORAGES` + `CSRF_TRUSTED_ORIGINS` before Django 6.1 bump
3. [ ] Bump Django/Unfold/Ninja via uv, `migrate + collectstatic`, screenshot dashboard+docs
4. [ ] Rewrite `install.* + Dockerfile` to uv, fix migrate-order bug, `docker build+run` smoke (`/health`, `/organization`)
5. [ ] Deprecate 7 non-PIM endpoints with `Sunset` headers, scaffold empty `catalog/, inventory/, procurement/`
