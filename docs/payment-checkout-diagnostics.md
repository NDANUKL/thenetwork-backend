# Checkout rejection diagnostics

10 November 2026, source only. Checkout Error Log entries retain bounded HTTP/provider status codes and a fixed reason category derived from provider text in memory. Categories are diagnostic hints, not proof of cause. Unknown responses remain UNCLASSIFIED. Raw response bodies, provider messages, URLs, arbitrary error codes and credentials are never logged. Existing reconciliation codes, retry rules and payment verification remain unchanged.

Deploy the native backend revision through the normal release workflow and restart application workers. No schema change or retired script installation is required. Verify on staging with an approved sandbox checkout. This change cannot reconstruct the discarded response for attempt 16msdaj4eu. Confirm that attempt against provider records before any operational resolution; do not clear Review or create a replacement order merely to collect diagnostics. No live records are changed by this source update.
