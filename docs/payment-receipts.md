# Payment receipts

The customer Billing page offers quotation downloads and payment receipts. The Receipts section lists a separate document for each verified deposit or balance payment. These receipts acknowledge payment and are not eTIMS tax invoices; tax invoicing remains a separate business process.

`fieldpulse.payment_receipts` checks request ownership, the payment status and its linked Pesapal attempt, matching payment ID, amount, currency, confirmation code and verification timestamp before rendering a receipt. Reversed, unpaid or mismatched payments have no receipt download. Sandbox payments render an explicit test-payment banner. Historical payment currencies are retained.

The template at `fieldpulse/templates/payment_receipt.html` shares the quotation logo, Carlito fonts, teal headings, navy total and A4 margins through the existing quotation PDF renderer. No new DocType or stored receipt file is needed; downloads render from verified records. Deploy both the backend module/template and website receipt route. Existing disabled script records are unchanged. The compatibility customer payment API also dispatches `download_receipt` to the same owned endpoint.

Validated with backend ownership/payment checks, frontend download route tests, a mocked browser download, and a visually inspected one-page fictional PDF. Test receipt PDFs are stored in the website workspace output folder, not production.
