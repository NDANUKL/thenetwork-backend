# R2 evidence configuration

FieldPulse reads R2 credentials exclusively from Frappe site configuration via
`frappe.conf`; neither credentials nor bucket names are stored in this repo.

For staging, configure:

- `r2_dev_access_key_id`
- `r2_dev_secret_access_key`
- `r2_dev_endpoint`
- `r2_dev_bucket`

For production, configure the corresponding `r2_prod_*` keys. If both sets
are configured on the same site, also set `r2_environment` to `dev` or `prod`.
If only one complete set exists, it is selected automatically.

The simple evidence flow is: request a short-lived presigned PUT URL, upload
directly to the private bucket, then call confirmation so the backend verifies
the object ETag and size with an R2 HEAD request. No file bytes or R2
credentials pass through Frappe or the mobile app.
