# Changelog

All notable changes to the M365 Copilot Prompt Analyser are recorded here.
Versions follow [Semantic Versioning](https://semver.org/).

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
