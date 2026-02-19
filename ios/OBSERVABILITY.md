# iOS Observability (Release Readiness)

## Scope

Internal diagnostics only. No external SDK. No user-facing feature changes.

## Components

- `DiagnosticsReporter` (in `TonieFinder/Sources/TonieFinderApp.swift`)
  - emits `api_error` and `non_fatal` events
  - default output is silent
  - output is enabled only when `TF_DEBUG_LOG=1` (or equivalent truthy value)
- `Diagnostics.reportMappedError(...)`
  - wraps `APIError.map(...)`
  - keeps existing `APIError.userMessage` behavior
  - forwards flow/path/status/error metadata to reporter

## Event fields

- `category`: `api_error` | `non_fatal`
- `flow`: `auth` | `pricing` | `watchlist` | `alerts` | `api_client`
- `endpointPath` (optional)
- `statusCode` (optional)
- `errorType`
- `message` (sanitized)
- `context` key/value map (sanitized)

## Privacy / Sanitization rules

Reporter must never log secrets or personal data:

- Authorization headers / bearer tokens
- token/access_token/auth_token values
- password-like fields
- email addresses

Sanitization is applied to both free text and context map fields.

## Local usage

Enable diagnostics + API request status logs:

```bash
TF_DEBUG_LOG=1
```

Default (`TF_DEBUG_LOG` unset or `0`) is silent diagnostics output.
