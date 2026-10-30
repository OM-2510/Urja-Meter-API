# Reflection

**What assumptions did you make?**
- I assumed that all timestamps returned by the legacy portal are in Indian Standard Time (IST, +05:30), as no timezone data was provided. 

- I also assumed the dataset is essentially static (the most recent consumption data ends on 30/06/2026), which justified using a simple, in-memory TTL cache without complex invalidation logic. 

- Finally, because the portal returns HTTP 200 for failed logins, I assumed it was strictly necessary to parse the JSON response body (`type: redirect`) to verify authentication success.

**Which part was the most difficult, and how did you get unstuck?**
The most challenging part was reverse-engineering the cryptographic signature (`x-signature`) required for the `/portal/export` endpoint. My initial attempts to guess the HMAC payload format using common combinations (like joining the path and query, or hashing just the timestamp) all failed. I got unstuck by digging into the browser's DevTools, tracking down the minified JavaScript file (`4.2Bgc2kUI.js`), and extracting the exact four-line message payload structure (`GET \n /portal/export \n page=1 \n {timestamp}`). 

**If you had another day, what would you improve?**
- I would replace the synchronous `requests` library with an asynchronous HTTP client like `httpx`. Right now, heavy data fetches could block the FastAPI event loop under high load. 

- I would also take the time to recursively reconstruct the flat `hierarchy` data from the export endpoint into a dedicated, navigable tree endpoint (Zone -> Circle -> Division -> Substation -> Feeder -> DT -> Meter).

**What mistake did you make while solving this (there's always one)?**
- I initially tried to hand-build the query strings for the `/portal/meters/search` endpoint. This immediately broke when I encountered meter manufacturers with ampersands in their names (like `L&T`), which corrupted the URL parameters. I fixed this by passing the parameters as a dictionary to the HTTP library, allowing it to handle proper URL encoding.

I spent too much time in hit and trial of composing the x-signature by trying various combinations of parameters and separators (like just the timestamp, or path and query joined) in an HMAC tool. Instead of blindly guessing, I should have gone straight to the minified frontend JavaScript (4.2Bgc2kUI.js), which explicitly contained the exact four-line payload recipe.

**If you were reviewing your own submission, what would you criticise?**
- I would point out that the API is highly fragile to UI changes. Because I chose the "Bulk Path" to avoid N+1 requests, the entire service relies on the portal's custom frontend HMAC signing scheme. If the Flock team changes how that signature is generated in the portal's frontend, this API adapter will instantly break. 

- Additionally, without a persistent local database (like SQLite or Postgres), a server restart means a "cold cache," requiring the API to hit the legacy portal heavily on the first few requests.

- The test could be integrated with github actions.