# Ground Scouts browser beta deployment

The Expo web client is built from `DiasporaDesk/mobile` and served from the Frappe site at `/groundscouts/`. The browser uses the same site origin, a Frappe session cookie, account-specific SQLite WASM storage, and IndexedDB for media recovery. Android storage and session handling remain on their native implementations.

## Build and package

From the mobile checkout, set `APP_VARIANT=staging`, set `EXPO_PUBLIC_APP_VARIANT=staging`, and set `EXPO_PUBLIC_FRAPPE_URL` to the exact HTTPS origin that will serve the web beta. Set `FRAPPE_APP_PATH` to this backend app directory if it is not at the script's default sibling path. Then run `npm run build:web-beta`.

The script exports a single-page app, copies its static files into `fieldpulse/public/groundscouts/`, and writes the SPA entry page to `fieldpulse/www/groundscouts.html`. Commit those generated files with the mobile and backend source changes that they correspond to. This enables Frappe's `/assets/fieldpulse/groundscouts/...` static URLs while keeping Expo routes under `/groundscouts/`.

The Frappe route rules in `hooks.py` return the SPA entry page for `/groundscouts/` and its deep links, including refreshes. The response hook adds the SQLite-required `Cross-Origin-Embedder-Policy: credentialless` and `Cross-Origin-Opener-Policy: same-origin` headers only for the app route. Verify the deployed app page reports `crossOriginIsolated === true`, `SharedArrayBuffer` exists, and the SQLite WASM worker loads.

## Storage and evidence upload configuration

Configure the R2 bucket's CORS policy for the exact HTTPS beta site origin. Permit `PUT` and the signed upload headers returned by the existing presign endpoint; expose the `ETag` response header so the client can confirm uploads. Keep this origin-specific. Test a photo and video presigned upload and confirmation on the deployed site.

Browser drafts require site storage. Safari may evict website data when device storage is low or the user clears website data; testers should keep the beta site data and review Device & storage for the current quota/recovery status. Assignment loading and submission require an active network connection.

## Release checks

1. Deploy the backend Python changes and generated static assets through the normal Frappe app release workflow. Local source is not proof of deployment.
2. Verify `/groundscouts/`, a direct task deep link, and refresh over HTTPS. Confirm the app path's isolation headers without applying them to unrelated site paths.
3. Verify the beta backend has the client-compatible Task Brief, auth, privacy, profile, finance, and notification APIs.
4. Verify the Frappe session cookie is HttpOnly, Secure, and scoped to the site; verify sign-out clears it and POSTs carry a valid CSRF token.
5. Configure the R2 CORS policy described above, then test uploads and exposed ETags.
6. Complete the sign-up, MFA, recovery, task, receipt, profile, notification, and sign-out journeys in Safari on a physical iPhone before sharing the beta URL.
