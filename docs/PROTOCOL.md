This document details the reverse-engineered behavior of the legacy Urja Meter Ops portal (`https://urja-ops.flockenergy.tech`).

## Endpoint Index

| Endpoint | Method | Auth Required | Purpose |
| :--- | :--- | :--- | :--- |
| `/login` | POST | Origin header | Authenticates operator, sets session cookie |
| `/api/auth/sign-out` | POST | Cookie + Origin | Invalidates session |
| `/portal/meters/search?q=&page=` | GET | Cookie | Basic meter list pagination (lite fields) |
| `/portal/dts?page=` | GET | Cookie | Transformer (DT) list pagination |
| `/portal/export?page=` | GET | Cookie + Signature | Bulk extraction (metadata, geo, hierarchy) |
| `/portal/keys` | GET | Cookie | Retrieves HMAC signing secret |
| `/portal/meters/{meterId}/geo` | GET | Cookie | Individual meter coordinates |
| `/portal/meters/{meterId}/energy`| GET | Cookie | Half-hourly consumption registers |

## Authentication & Session lifecycle

* **Login Payload:** Requires `email` and `password` sent as `application/x-www-form-urlencoded`. The `Origin` header is strictly enforced.
* **Login Responses:** The portal returns HTTP 200 for *both* success and failure. Status must be read from the JSON body. A success returns `{"type":"redirect","status":303,"location":"/meters"}` and sets `__Secure-better-auth.session_token`.
* **Session Expiry:** A dead session returns a JSON body `{"error":"unauthorized"}` with HTTP 401. 
* **Sign-out:** Requires the `Origin` header. It is idempotent; firing a sign-out request with an already dead cookie still returns `{"success":true}`.

## Data Extraction: Two Assembly Paths

The portal's endpoints allow a complete meter profile to be assembled in two distinct ways:

### Path 1: Granular Assembly (Cookie Auth Only)
A client could theoretically scrape the portal by combining:
1. `/portal/meters/search` for basic nameplate data.
2. `/portal/meters/{meterId}/geo` for coordinates.
3. `/portal/meters/{meterId}/energy` for consumption.
* **Pros:** Does not require breaking the cryptographic signature.
* **Cons:** Creates massive N+1 request overhead (requires separate geo and energy calls per meter) and misses out entirely on the detailed network hierarchy structure.

### Path 2: Bulk Export (Requires Signature)
The portal features an underlying bulk export route that is heavily secured:
1. `/portal/export` yields full nameplate, geo, and hierarchy data for all meters simultaneously.
2. `/portal/meters/{meterId}/energy` is still required to fetch consumption.
* **Pros:** Highly efficient, providing the complete network hierarchy and geolocation mapping in one call.
* **Cons:** Demands generating a strict, time-sensitive cryptographic signature for the export call.

### The Export Cryptographic Signature Details
To utilize the Bulk Export path, the client must fulfill the following:
* **Required Headers:** `x-timestamp` (Unix seconds) and `x-signature`.
* **The Key:** The backend intentionally exposes the `signingSecret` to the client via `/portal/keys`.
* **The Message Payload:** Four newline-separated strings containing the HTTP Method (`GET`), URI path (`/portal/export`), Query string (e.g., `page=1`), and the `x-timestamp`.
* **The Hash:** An HMAC-SHA256 lowercase hex string.
* **Replay Window:** Signatures are valid for a very brief window (~2-3 minutes) before failing with a 401 `signature_invalid`.

### Consumption Data Details
* The `/portal/meters/{meterId}/energy` endpoint requires no signature, only the cookie.
* Timestamps are returned as `dd/mm/yyyy hh:mm` in 30-minute intervals. No timezone is provided.
* `kwh` and `kvah` are cumulative registers. Consumption for a specific half-hour interval must be calculated by finding the delta between consecutive rows.

## Irregularities & Quirks

* **Data Types:** Almost all numerical data, including latitude, longitude, and consumption metrics, are returned as strings by the standard API endpoints. The bulk export endpoint, however, formats `lat`/`lng` as actual numbers.
* **Pagination Behavior:** Requesting an out-of-range page does not throw a 404. It returns HTTP 200 with an empty `data` array.
* **Inconsistent Network Codes:** DT-029 is tied to `feederCode` F-001, whereas most other distribution transformers map directly to their corresponding feeder numbers (DT-N maps to F-N).
* **Stale Data:** The latest consumption data cuts off at 30/06/2026. Meters marked as "Decommissioned" still return historical reading arrays up to that date.

## Dead Ends

* **Brute-forcing the Signature:** Guessing the signature payload format using standard combinations (timestamp alone, path+query joined, standard separators) in an HMAC tool failed. The exact recipe is tightly coupled to the custom frontend Javascript and required manual source code inspection.
* **Exporting without Signatures:** Attempting to hit the bulk export with just the session cookie immediately yields a 401 Unauthorized `signature_invalid` error.