# Urja Meter Ops: investigation notes

Portal: https://urja-ops.flockenergy.tech

Method: found via browser DevTools (Network tab, Keep log on), then reproduced with curl.

All data endpoints live under `/portal/` and need the session cookie.

## Endpoint index

| Endpoint | Method | Auth | Purpose | Section |
| ----- | ----- | ----- | ----- | ----- |
| /login | POST | Origin header | log in | 1.1 |
| /api/auth/sign-out | POST | cookie + Origin | log out | 1.3 |
| /portal/meters/search?q=&page= | GET | cookie | meters list (lite fields) | 2.1 |
| /portal/dts?page= | GET | cookie | DT (transformer) list | 2.2 |
| /portal/export?page= | GET | cookie + x-signature + x-timestamp | full meter records (geo + hierarchy) | 2.3 |
| /portal/keys | GET | cookie | returns signingSecret | 2.4 |
| `/portal/meters/{meterId}/geo` | GET | cookie | meter coordinates | 2.5 |
| `/portal/meters/{meterId}/energy` | GET | cookie | half-hourly consumption | 2.6 |


## 1. Auth and session

### 1.1 Login

* Request: `POST https://urja-ops.flockenergy.tech/login`

* Payload fields: `email`, `password`

* Request body Content-Type: `application/x-www-form-urlencoded`

* Response body Content-Type: `application/json`

* HTTP status is 200 for both success and failure. The real outcome is in the JSON body (`type`, `status`). Browser requests carry `x-sveltekit-action: true` and `Accept: application/json`, which points to a SvelteKit form action.

Success body (also sets the cookie):

```
{"type":"redirect","status":303,"location":"/meters"}
```

Failure body (no cookie):

```
{"type":"failure","status":401,"data":"[{\"email\":1,\"error\":2},\"operator@urja.local\",\"Invalid email or password.\"]"}
```

Cookie set on success:
`__Secure-better-auth.session_token=REDACTED; Max-Age=3600; Path=/; HttpOnly; Secure; SameSite=Lax`

Minimum request to log in (tested in curl by removing headers one at a time):

* Header `Origin: https://urja-ops.flockenergy.tech`: required

* Body `email=...&password=...` (form-urlencoded; curl adds the Content-Type automatically)

### 1.2 Session

* Proof of login: cookie `__Secure-better-auth.session_token`, initial `Max-Age=3600` (1 hour)

* Data call with a dead or missing session: 401 Unauthorized, Content-Type `application/json`, no redirect (seen in the browser after killing the session from curl).
  Body: `{"error":"unauthorized","message":"A valid session is required."}`

### 1.3 Sign-out

* Request: `POST https://urja-ops.flockenergy.tech/api/auth/sign-out`

* Needs the `Origin` header and the session cookie.

  * No Origin -> `{"code":"MISSING_OR_NULL_ORIGIN","message":"Missing or null Origin"}`

  * OK -> 200 `{"success":true}`

* After sign-out the old cookie no longer returns data (session invalidated server-side).

* Idempotent: repeating it with an already-dead cookie still returns 200 `{"success":true}`.

* Clears 3 cookies via `Max-Age=0`: `session_token`, `session_data`, `dont_remember`.

## 2. Data endpoints

### 2.1 Meters list

* Request: `GET /portal/meters/search?q=&page=1`, requires cookie only (tested in curl)

* Returns: `{"data":[...],"total","page","pageSize"}`

* Fields: `meterId`, `serialNo`, `make`, `phaseType`, `installStatus`, `dtCode`

* Pagination: page size 20, 403 meters total

* `q` matches `meter ID` or `serial number` only

* Out-of-range page (e.g. 23):

  * Status: `200`

  * Response Body: `{"data":[],"total":403,"page":23,"pageSize":20}`

* Values containing `&` break hand-built query strings; pass params through the HTTP library

### 2.2 DT (transformer) list

* Request: `GET /portal/dts?page=1` (cookie required; fired from the `/transformers` page)

* Returns: `{"data":[...],"total","page","pageSize"}`

* Fields: `code`, `name`, `feederCode`, `capacityKva`

* Pagination: page size 20, 40 DTs total (2 pages)

* Out-of-range page:

  * Status: `200`

  * Response Body: `{"data":[],"total":40,"page":3,"pageSize":20}`

### 2.3 Export (bulk path)

* Request: `GET /portal/export?page=1`, cookie + `x-timestamp` + `x-signature` required

* Returns: `{"data":[...],"total"}`

* Fields: everything in 2.1 plus `installType`, `build`, `geo` (`lat`, `lng`), `hierarchy` (`zone`, `circle`, `division`, `subdivision`, `substation`, `feeder`, `dt`; each with `name`, `code`)

* `x-timestamp`: Unix time in seconds, generated at signing time.

* `x-signature`: HMAC-SHA256 (lowercase hex) of four lines joined by newlines: `GET`, `/portal/export`, `page=N`, timestamp. Key: `signingSecret` from `/portal/keys` (UTF-8).

  * Recipe read from the page's JS (`4.2Bgc2kUI.js`) and verified by reproducing a browser signature in an HMAC tool.

  * The signature covers the page, so a signature for `page=1` is rejected on `page=2` (tested in curl).

* Without a valid signature:

  * Body: `{"error":"signature_invalid","message":"Missing or invalid request signature."}`

  * Status: 401 Unauthorized

* Replay window: a browser-copied signature worked within ~2-3 min and failed on a later replay (not measured exactly).

* **🔴 TODO:** Pagination not tested (needs a valid signature for `page=2`; the portal's own Export button requests only `page=1`, read from the page's JS).

### 2.4 Signing key

* `GET /portal/keys`, cookie only, returns `{"data":{"signingSecret":"<REDACTED>"}}`

* Confirmed: this secret is the HMAC key for `x-signature` (see 2.3)

* The page fetches it before each export. **🔴 TODO:** whether it stays the same across logins (compare two logins in the Python client).

### 2.5 Meter geo

* Request: `GET /portal/meters/{meterId}/geo`, cookie only (tested in curl on J100008)

* Returns: `{"data":{"latitude":"...","longitude":"..."}}`; both values are strings

* Export carries the same data as `geo` with numeric `lat`/`lng`. On J100000 the detail page's Location matched the export record.

### 2.6 Meter energy (consumption)

* The meter page `/meters/{meterId}` (seen for J100000 and J100008) shows Nameplate, Location, a hierarchy breadcrumb and a Consumption table. It is fed by the `geo` and `energy` requests plus SvelteKit's `__data.json` page-load call (not used by the API).

* Request: `GET /portal/meters/{meterId}/energy`, cookie only (tested in curl on J100008); no query params and no signature headers

* Returns: `{"data":[{"timestamp","kwh","kvah","voltR"}, ...]}`; all values are strings

* `timestamp` format: `dd/mm/yyyy hh:mm`, 30-minute steps, no timezone

* Window for J100008: 23/06/2026 23:30 to 30/06/2026 23:30 (7 days), matching "Latest: 30/06/2026 23:30" on the page

* `kwh` and `kvah` rise on every row in this sample (looks like a cumulative register, so use during an interval = difference between consecutive rows; inferred). `voltR` stayed between 220 and 240.

* **🔴 TODO:** Row count per meter: count in code (337 expected if there are no gaps).

## 3. Irregularities Mapping

* **`/login` Endpoint:**

  * Login failure deceptively returns HTTP 200; the real result is hidden in the JSON body.

  * The failure `data` field is an unusual flattened array where keys point to array positions.

  * Immediately rejects requests if the `Origin` header is missing.

* **`/api/auth/sign-out` Endpoint:**

  * Missing `Origin` header results in request rejection.

  * Wrong HTTP method (e.g., GET) returns 404 instead of 405.

  * Action is idempotent and always says success, even if the session is already dead.

* **`/portal/meters/search` Endpoint:**

  * Characters like `&` inside data values (e.g., `L&T`) will break hand-built query strings if not explicitly handled by the HTTP library.

* **`/portal/export` Endpoint:**

  * Outlier endpoint requiring a strict time-based cryptographic signature (`x-signature` and `x-timestamp`), while other data endpoints (`search`, `dts`, `geo`, `energy`) only need the cookie.

* **`/portal/keys` Endpoint:**

  * Unconventionally hands the backend signing secret to any logged-in client user.

## 4. Data quirks (spotted with AI help in sample responses) **🔴 TODO:** verify against the full export data in code

* `build` has more than one value: `legacy` and `v2` (seen on J100004).

* `make` includes `Secure` alongside the other makes.

* DT-029 has `feederCode` F-001, while other DTs map DT-N to F-N.

* Same data, different shapes: the `geo` endpoint returns `latitude`/`longitude` as strings; export returns `lat`/`lng` as numbers.

* `energy` returns every value as a string, and timestamps as `dd/mm/yyyy hh:mm` with no timezone.

* The consumption data ends on 30/06/2026 23:30 for the meters checked (J100000, J100008), about four months before the investigation date (29 Oct 2026). J100000 is Decommissioned but still has readings.

* Zone and circle codes repeat across the meters sampled (Z-01 to Z-03 and C-01 to C-06 cycling), while division, subdivision, substation, feeder and DT numbering follows the DT number.

## 5. Dead ends

* Export with only the cookie, or with an old signature/timestamp: rejected with `signature_invalid`.

* Guessed the signature message format in an HMAC tool (timestamp alone, path+query joined, various separators): no match. Reading the page's JS gave the real recipe (method, path, query and timestamp on separate lines).

## 6. Open questions

* **🔴 TODO:** Export `page=2` and above with a valid signature.

* **🔴 TODO:** Whether `signingSecret` changes between logins.

* Whether `energy` accepts query params: not tested (the browser sends none; the API filters dates itself).

* Where the detail page gets its nameplate and breadcrumb: probably its `__data.json` load, not inspected (export carries the same fields).

## 7. AI use log

* Used Claude as a tutor to learn Chrome DevTools, to structure these notes, and to explain the minified signing function after I pasted it from the page's JS.

* Claude suggested where to look (the Initiator tab) and supplied a generic HMAC snippet and the candidate message formats I tried (those failed, see Dead ends).

* Endpoint discovery, the header tests, the curl reproductions and verifying the signature match were done by me.

* Claude drafted section 8 (design decisions) from my findings.

* **🔴 TODO:** Update this log once the Python client is written (what I wrote myself, what AI reviewed).

## 8. Design decisions (draft for the README) **🔴 TODO:** review and edit so every line is a decision I can defend

* **Stack:** Python + FastAPI (typed models, `openapi.json` generated automatically), `requests` for portal calls.

* **Structure (kept small):**

  * `portal/client.py`: the only code that talks to the portal (login, cookie, signing, re-login and retry)

  * `schemas.py`: clean response models

  * `service.py`: caching and merging of portal data

  * `main.py`: FastAPI routes

* **Data sources:**

  * Meters from `/portal/export`: one call returns nameplate, geo and hierarchy for all 403 meters (~231 kB).

  * Transformers from `/portal/dts`: the only source of `capacityKva` (2 pages).

  * Consumption from `/portal/meters/{meterId}/energy`, fetched per meter on demand.

  * `search` and `geo` are not used: both are subsets of export. Trade-off: the API depends on the signing scheme, and there is no fallback if the portal changes it.

* **API surface (draft):** `GET /meters` (filters + pagination), `GET /meters/{meter_id}`, `GET /meters/{meter_id}/consumption` (optional `from`/`to`), `GET /transformers`, `GET /transformers/{code}`, `GET /health`. A hierarchy tree endpoint only if time remains.

* **Normalisation:** numbers returned as numbers, timestamps as ISO 8601, coordinates as numeric `lat`/`lng`. Assumption: the portal's timestamps are local Indian time (IST, +05:30), since the portal states no timezone.

* **Session and signing:**

  * Log in lazily and reuse the cookie. Read login success from the JSON body (`type: redirect`), not the HTTP status.

  * A dead session and a bad signature both return 401, so the client reads the body `error`: `unauthorized` means log in again and retry once; `signature_invalid` means sign again with a fresh timestamp and retry once.

  * Fetch `signingSecret` at runtime and never store it. Credentials come from environment variables (`.env`, not committed).

* **Caching:** export and DT data cached in memory with a configurable TTL; consumption cached per meter. The data appears static (last reading 30/06/2026), so TTL-only expiry with no invalidation is low risk.

* **Errors:** unknown meter returns 404; a portal failure after one retry returns 502 with a clear JSON error.

* **Read-only and polite:** only GET calls plus login/logout, one shared session, no request bursts.

* **Tests (small):** message building and signature format with a dummy secret (the real secret never goes in the repo), login-failure body detection, energy normalisation, and one endpoint test with a stubbed portal client.

* **Intentionally skipped:** Postgres/local query index, web client, persistent cache, auth and rate limiting on my own API.