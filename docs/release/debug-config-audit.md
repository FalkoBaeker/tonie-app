# Debug/Release Config Audit (S7-02)

## Steuerung
- `#if DEBUG`: kapselt Debug-UI (Diagnostics-Card + Source-Zeilen).
- `AppConfig.debugLoggingEnabled`:
  - Debug-Build: folgt `TF_DEBUG_LOG` (env/plist).
  - Release-Build: immer `false` (hart erzwungen), unabhängig von Env Vars.

## Relevante Config Keys
- `TF_DEBUG_LOG` (nur Debug wirksam)
- `TF_API_BASE_URL`
- `TF_AUTH_MODE`
- `TF_SUPABASE_URL`
- `TF_PRIVACY_POLICY_URL`
- `TF_TERMS_URL`
- `TF_SUPPORT_URL`
- `TF_SUPPORT_EMAIL`

## Release-Verhalten (gewollt)
- Keine Debug-/Source-Daten im Account-Screen.
- Rechtliche Links nur mit validen, nicht-placeholder URLs (`http/https`, kein `example.com`, kein `<...>`).
- Support-E-Mail nur, wenn nicht-placeholder und formal plausibel.
