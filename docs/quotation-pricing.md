# Quotations: pricing and customer downloads

A quotation covers one request and one or more of its projects. Add one item per project; duplicate projects and projects belonging to another request are rejected. The Desk project selector filters by the quotation request.

Coordinators select a pricing mode for draft quotations: **Beta - KSh 1 per project** (KES, VAT inclusive), or **Live - USD 100 per project** (USD, VAT exclusive). Live remains the default. The backend derives currency and rate from the selected mode; manual rate overrides are not accepted. Switching modes resets the draft discount in Desk, since a discount in one currency is not a currency conversion. Historical non-USD drafts without a mode require an explicit selection before repricing.

The project picker excludes projects already selected. Duplicate entries are cleared immediately, with an explanatory message; form validation and backend validation also reject duplicates. Row rate and amount currency formatting follows the parent quotation currency.

Staff enter a fixed discount in the quotation currency, applied once to the combined project subtotal. Legacy percentage drafts are converted to the equivalent fixed discount. VAT defaults to 16%; beta prices include configured VAT, so one project costs KSh 1 before any discount, while live prices add VAT to the discounted USD subtotal. Existing 50% deposit and balance rules remain; neither payment may be zero. The payment provider must accept the resulting small KES instalments for beta checkout to succeed; local tests do not verify provider acceptance.

Issued and accepted quotations remain locked and retain recorded totals. Legacy quotations without a saved pricing breakdown display their recorded total and instalments without inventing VAT. Withdraw an unpaid issued quote and prepare a replacement to change its scope or pricing.

The customer billing section includes Download quotation. The same-origin route verifies the customer session and forwards only that customer's Frappe session. The backend checks verified account ownership of the request before rendering its current issued or accepted quotation. PDFs contain commercial scope, pricing, dates and terms; live scout assignments stay in the portal.

## Deployment and verification

Deploy the backend first and run normal Frappe migration to sync DD Quotation fields and the standard Diaspora Desk Quotation print format. Then deploy the frontend. Native runtime uses fieldpulse.payments.download_quote; the native dd_payments compatibility dispatcher also handles download_quote. This change does not update or reactivate historical Server Scripts. An installation still running active legacy scripts must finish its separately authorized native handover before using this feature.

In staging, save and issue a two-project quotation with a percentage discount and with a fixed discount; verify VAT-exclusive and VAT-inclusive rates, PDF download, customer acceptance, checkout amounts and the existing verified-deposit assignment gate. Confirm another customer's request cannot be downloaded. Check a legacy accepted quotation retains its recorded total. Verify the PDF with the deployed wkhtmltopdf renderer, including long scopes and terms. Local Chromium previews fit ordinary one- and two-project examples on one page; longer content may flow onto additional pages.

Offline validation: Python unit tests cover pricing, project membership, issued quotation locks and PDF ownership. Frontend tests cover customer-session forwarding in both native and compatibility routing, private download responses and error handling. Production migration, live payments and wkhtmltopdf acceptance require a Frappe staging environment.

## Branded quotation layout

The print format follows the owner's quotation reference: compact quotation/customer metadata, a teal three-column service table, pale item rows, right-aligned totals, and terms below. The header uses the bundled DD logo. Navy and teal replace the reference's green. There is no handwritten acceptance, name, date, or signature section; acceptance remains in the customer portal.

Carlito Regular and Bold are bundled under the SIL Open Font License as Calibri-compatible fonts. Customer downloads embed those fonts and the logo as data URIs through fieldpulse.quotation_pdf, so authenticated PDF generation does not depend on external font services or fetching the logo over HTTP. Native Desk printing uses the same bundled public assets through the site URL. Deploy assets with the backend, then migrate to sync the standard print format. Verify both native Desk print and authenticated downloads on the deployed wkhtmltopdf version; Chromium preview checks do not establish wkhtmltopdf parity.

The template preserves recorded totals, discounts, VAT-inclusive/exclusive breakdowns, 50/50 instalments, and legacy quotes without a stored tax breakdown. Long item descriptions may flow across pages; table headers repeat, and totals and instalments stay grouped.

## Download font compatibility

The production download was observed falling back to Nimbus Sans despite serving the custom TTF assets. The print format now uses the native Carlito family name, WOFF-first font sources, and explicit table/heading font inheritance. The authenticated download embeds both WOFF and TTF sources; Desk printing uses the matching public assets. Both regular and bold files must ship.

Use the deployed wkhtmltopdf renderer to verify output, not only a browser preview. Run tools/verify_quotation_fonts.py against a freshly downloaded PDF; it fails if Carlito regular/bold are missing or another font substituted. Restart backend workers after deploying quotation_pdf.py, and migrate to sync the print format. A font file returning HTTP 200 does not prove it was used in the PDF.

### Linux renderer font isolation

The initial user-font registration guard caused live download failures: Error Log reported PDF renderer substituted Carlito Regular. It compared one globally resolved file path with a required user-directory path and blocked generation. That guard and user-font installation have been removed.

Quotation rendering retains Frappe prepare_options/cleanup (private-image/cookie preparation and temporary-file cleanup) and the JavaScript/local-file restrictions. It passes a copied environment to pdfkit for this render only. On Linux, FONTCONFIG_FILE points to a temporary configuration containing the bundled quotation font directory and an isolated cache. This bypasses the server's global font selection without modifying worker environment variables or user/system font directories. No fc-match/fc-cache gate can prevent a quotation download.

Deploy both fieldpulse/payments.py and fieldpulse/quotation_pdf.py and restart web workers. Updating the Print Format record alone cannot apply a Python rendering fix. Verify a new website download succeeds, then inspect that exact PDF with tools/verify_quotation_fonts.py. Local mocks and the Windows wkhtmltopdf test do not establish Linux production parity.

29 October 2026: selectable beta/live pricing and immediate duplicate checks implemented locally. Requires normal deployment/migration and Desk/payment verification; not proof of live activation.

29 October 2026 owner-authorized temporary staffing change: the quotation planned scout count no longer caps assignments. Coordinators may allocate additional scouts without changing the per-project price. Dispatch still requires the accepted quotation to include the project and a verified 50% deposit in the current payment environment. Existing assignment, access and Task Brief checks remain. Requires normal backend deployment.
