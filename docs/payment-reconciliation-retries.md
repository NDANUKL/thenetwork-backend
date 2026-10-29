# Pesapal reconciliation retry control

Source change: 30 October 2026. Not evidence of deployment.

The five-minute scheduler remains, but only due Pending/Review attempts with a tracking ID in the currently selected payment environment are considered. Disabled checkout pauses automatic reconciliation. Sandbox attempts remain intact when live is selected, and vice versa; IPN and customer refresh continue to use the existing verification rules.

Failed verification records durable read-only retry metadata on DD Payment Attempt: consecutive failures, next automatic verification, last failure code and last failure time. Delays are 15, 30, 60, 120, 240, 480, 960 and then 1440 minutes. Daily attempts continue so missed provider notifications can eventually recover; this is a retry-frequency cap, not abandonment of a payment. A successful scheduler verification resets this metadata. Provider notifications and explicit customer refresh bypass the scheduler delay and still require verified provider status.

One site-scoped lock prevents overlapping scheduled batches. The database selects due attempts before applying its 100-record limit. Failure handling rolls back verification first, then saves only retry metadata. It never marks an attempt paid/failed, deletes records or changes verification requirements. Error Log records only the first failure or a changed reason; unchanged failures remain visible on the attempt without duplicate logs. Logs contain fixed failure codes, not provider messages, bodies, URLs or credentials. Existing Error Logs are retained.

Deploy the native backend revision and run ordinary Frappe migration to add the four fields before running the revised job. Do not modify or enable retired Server Scripts. Verify scheduler execution, due-date filtering and overlapping-worker locking on a backed-up staging site; unit tests use mocked Frappe/Redis and do not prove live migration or provider connectivity. No mobile build is needed for this change.
