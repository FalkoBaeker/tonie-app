# eBay Runtime Environment Setup (S8-01)

Stand: 2026-02-20

## Pflicht-Variablen (Backend Runtime)

```env
EBAY_API_ENABLED=true
EBAY_ENV=production
EBAY_CLIENT_ID=<from-ebay-developer-portal>
EBAY_CLIENT_SECRET=<from-ebay-developer-portal>
EBAY_MARKETPLACE_ID=EBAY_DE
```

## Empfohlene robuste Defaults

```env
EBAY_REQUEST_TIMEOUT_S=15
EBAY_MAX_RETRIES=2
EBAY_API_SHADOW_MODE=true
EBAY_API_INCLUDE_IN_PRICING=false
```

## Weekly Refresh Policy

```env
MARKET_AUTO_REFRESH_ENABLED=true
MARKET_AUTO_REFRESH_INTERVAL_MINUTES=10080
```

## Sicherheitsregeln
- Secrets niemals committen.
- Nur im Backend-Runtime-Environment setzen (`backend/.env` lokal oder Secret Manager im Hosting).
- iOS-App bekommt niemals `EBAY_CLIENT_SECRET`.

## Verifikation
- Ohne vollständige eBay Credentials meldet die API intern einen klaren Config-Issue.
- Mit Credentials kann der neue eBay-Auth-Layer OAuth Tokens abrufen und Browse-Requests ausführen.
