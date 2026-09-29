# Changelog

All notable changes to the M365 Copilot Prompt Analyser are recorded here.
Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Suite consistency pass — the four Copilot reporting solutions share one
architecture, and this brings Prompt Analyser back into line with its siblings.
Spec: [`docs/specs/suite-consistency-pass.md`](docs/specs/suite-consistency-pass.md).

### Fixed

- **A fresh image could not start.** SQLAlchemy 2.x only pulls in greenlet via its
  `[asyncio]` extra, and both the dependency list in `pyproject.toml` and the
  duplicate one in the `Dockerfile` asked for plain `sqlalchemy`. Any newly built
  image therefore raised `ImportError` from `shared.db` and the api and worker
  containers crash-looped — which meant a one-click Azure deploy from `main` did
  not come up. Existing deployments were unaffected because their images were
  built when greenlet happened to arrive transitively.
- **Microsoft 365 E7 users were invisible.** Copilot licences were matched against
  a configured list of SKU IDs that shipped containing only the Microsoft 365
  Copilot SKU, so E7 — which bundles Copilot — was never counted, and neither was
  the second Microsoft 365 Copilot SKU, Copilot for Sales or the education SKU.
- **Demo data showed people as raw ids.** The seeder never wrote `entra_users`, and
  every person, department, country and manager slicer is built from that table, so
  a demo-seeded instance listed `user-00` with four empty slicers.
- **The personal pages could not be opened without Entra**, which meant anyone
  evaluating the product never saw pages the README advertises.
- **Two working pages were unreachable.** Historical backfill and the Setup guide
  were routed but linked from nowhere.
- KPI tiles rendered a grid row ragged when only some tiles had a subtitle.

### Added

- **Administrators by Entra group.** An optional admin group object ID in Settings
  grants administrator rights to its members when they sign in with Entra, so
  administration no longer means sharing one password. It **fails closed**: unset
  grants admin to nobody. Membership is read per request, so removing someone bites
  within minutes rather than at their next sign-in. The local admin account is
  unaffected and remains the way in.
- **The signed-in person is shown by name.** The ID token always carried the display
  name and the app discarded it; the sidebar now shows display name, UPN and role.
- **Executive briefing** — this period against the last in plain English, reachable
  directly after Overview. Deterministic by design: every figure is SQL and every
  sentence is assembled from fixed thresholds, so it cannot invent a number in front
  of a customer even though the app has Azure OpenAI configured.
- **Tenant users** — the imported directory joined to the usage, with licence status,
  prompt counts and the manager resolved to a name. People with no activity are
  listed rather than filtered out, because an unused licence is the row worth
  finding. Org-gated, and every column can be filtered.
- A subtitle on every stat tile on **Your coaching** that says something the label
  does not — active days, prompts per conversation, how the person's quality compares
  with the organisation's, and how many of their prompts were their own words.

### Changed

- **Copilot licences are detected rather than configured.** Anyone holding a SKU that
  contains the *Microsoft Copilot with Graph-grounded chat* service plan
  (`3f30311c-…`) counts, derived live from the tenant's own `subscribedSkus`, and a
  bundle with Copilot in `disabledPlans` correctly does not. `copilot_sku_ids`
  survives as a manual override, and Settings shows which subscriptions matched.
- Demo data now seeds a fourteen-person directory with a reporting line, gives each
  person a different prompting skill so the coaching pages have someone to coach, and
  leaves two people licensed with no activity.
- Nav headings are `YOU` / `ORGANISATION` / `ADMINISTRATION` / `HELP`, with no item
  outside a heading.
- The Copilot mark is the current 510px export, and the favicon is a real 32px image
  rather than a byte-identical copy of the 388 KB logo.
- `DataTable` gained an opt-in per-column filter row; `ChartCard` gained an optional
  header action. Both match the shared components in the sibling solutions.

### Notes for existing deployments

- Three migrations, all additive: `0004_admin_group`, `0005_copilot_sku_autodetect`
  and `0006_demo_persona`. The middle one clears `copilot_sku_ids` **only** where it
  still holds the shipped default — a deliberately customised list is preserved, and
  can be emptied in Settings to opt into detection. Upgrade and downgrade were both
  verified against Postgres.
- Licence counts may go **up** after this upgrade, because E7 and second-SKU holders
  were previously missed. That is a correction, not a change in the tenant.

## [1.2.0] — 2026-09-25

### Changed

- **Azure OpenAI now uses the v1 API surface.** The analysis client is the plain
  `AsyncOpenAI` client pointed at `https://<resource>.openai.azure.com/openai/v1/`,
  replacing `AsyncAzureOpenAI` and the deprecated dated `api-version` query
  parameter. The deployment name travels in the request body as `model` rather
  than in the URL path. See the
  [API version lifecycle](https://learn.microsoft.com/en-us/azure/ai-services/openai/api-version-lifecycle)
  doc.
- **The endpoint you type is normalised for you.** `my-resource.openai.azure.com`,
  `https://my-resource.openai.azure.com`, `.../openai` and `.../openai/v1/` (with
  or without a stale `?api-version=`) all resolve to the same v1 base URL, so
  there is nothing to retype.

### Removed

- **The API version field is gone from Settings** and from the setup steps in the
  README — it no longer affects anything.

### Notes for existing deployments

- **No migration and nothing to roll back.** The `app_config.aoai_api_version`
  column is retained and simply ignored, so existing rows are untouched.
- `PUT /admin/config` still *accepts* an `aoai_api_version` field for wire
  compatibility with older clients, but ignores it. It is no longer returned by
  `GET /admin/config`.
- Structured Outputs behaviour is unchanged: `json_schema` is preferred, with the
  existing `json_object` fallback when a model rejects it.

## [1.1.0]

- Added an Overview page, tidied the navigation, and stopped the build stamp
  reporting a date nobody built on.
- Personal view on open, with the organisation view gated by group membership.
- Entra ID sign-in without Azure Easy Auth.
