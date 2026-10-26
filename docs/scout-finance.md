# Scout pay and mobile Earnings

## Simplified source workflow ? 26 October 2026

Production ownership is governed by [production-script-ownership.md](production-script-ownership.md).
Native handover is complete; that does not establish deployment or activation of
this finance feature or this simplification. These changes require normal native
deployment, schema migration and mobile release verification. No live changes were
made as part of this source update.

The daily workflow is: issue a scout agreement, obtain acceptance in mobile,
approve the submitted work, then record the successful external payment.
A task budget is optional. Work approval creates the earning automatically.
The Scout payments page lists accepted arrangements independently of budgets,
showing paid and remaining amounts and a Record payment action.

Customers continue paying through the existing Pesapal integration. Funds settle
into the business bank account, or an optionally linked Openfloat account. Staff
execute scout payments using their authorized business bank/M-Pesa access; no bank
login or balance is exposed in Frappe. Openfloat is not required.

Finance/System Manager records amount, channel, actual payment date, successful
transaction reference, masked recipient, recipient/amount confirmation and a
private receipt. This creates a confirmed payout with its allocation and audit
in one action. It does not repeat bank approvals or initiate a transfer. Duplicate
references, overpayments, unapproved earnings, held arrangements and reservations
from existing pending payouts are checked. Travel advances remain limited to the
accepted terms. The same work approver may record an already completed transfer;
this record is not authorization to release bank funds.

Mobile leads with agreed fee, travel, amount paid and remaining amount. The fuller
calculation is under View breakdown. Claims and recipient requests are optional.
Existing payment, refund, adjustment, budget, recipient and case records remain;
advanced workflows remain accessible through More/records for exceptions. Nothing
is deleted, and already pending transfers still require their original outcome
workflow. There is no automatic bank/Openfloat payout synchronization.

Verify staging with separate coordinator, Finance and scout accounts: agreement
without budget, accepted-offer/deposit gates, reviewed work, partial payments,
travel advance, duplicate retries, concurrent payouts, private receipt upload,
payment history and account-specific offline mobile snapshots. Confirm no retired
scripts are enabled and no payment is sent by Record payment.

## Retained advanced records and controls

The site flag `dd_finance_enabled` defaults off. Create the Finance role through
normal installation/migration; this does not assign any users. The owner chooses
which coordinators or other staff receive Finance. The Scout Finance workspace
and `/app/dd-finance` page are for Finance and System Manager. Operational
coordinators can read relevant arrangements/cases; releasing money requires
Finance. Scouts see only their own issued arrangements and earnings.

## Record a task arrangement

1. Create DD Task Budget against the customer's issued quotation. Its reporting
   currency and net service revenue come from that quotation, excluding VAT.
   Plan scout fees, travel, logistics, gateway fees, rework and other costs in
   separate rows, linked to projects/revisits where relevant. Mixed currencies
   require a recorded conversion rate and date; the system invents no FX rate.
2. Optionally alongside a budget, create DD Scout Offer for each scout/project. Record fee, fixed travel allowance
   or capped reimbursement, advance limit, expense conditions, payout terms,
   acceptance deadline and days due after approval. Issue it. The scout reads and
   accepts the exact hashed terms in Earnings while online, before dispatch.
3. With finance enabled, new assignment/revisit dispatch requires exactly one
   matching accepted arrangement. The existing deposit gate still applies. The
   simplified assignment dialog is unchanged. A revisit has its own authorised
   scope/cost agreement and offer, including explicit zero extra fee if applicable.
4. Coordinator approval of the submitted work creates one earning entitlement per
   accepted arrangement. Earnings are not automatically held for the customer's
   remaining balance. A complaint alone does not establish scout misconduct.

Existing assignments are not given invented fees or historical acceptance dates.
Create and obtain actual acceptance of their arrangement, then use **Bind existing
assignment**, with notes. This is an audited adoption, not a claim that agreement
predated dispatch. Already approved work needs its actual passed coordinator
review to create an entitlement. Resolve incomplete legacy records in staging
before adopting them; do not fabricate reviews. Tasks already in progress are
not blocked merely because they predate the finance feature.

## Claims, adjustments and recipients

Scouts submit travel/expense claims with a private PDF/JPEG/PNG receipt (up to
10 MB), or an explanation of alternative evidence. Finance approves or rejects
with notes and explicitly authorises alternative evidence. Fixed travel cannot
also be claimed as actual travel. Approved actual travel cannot exceed its cap.
Draft request UUIDs prevent a retry from creating a second claim.

Approved additions/deductions require a recorded agreement/lawful basis and
evidence or authorised alternative. No employment classification, tax rate or
withholding amount is inferred. Finance verifies classification and invoicing.
Corrections use reversing adjustments, preserving originals.

Scouts request a payment recipient in Earnings, or Finance uses **Request payment
recipient** on the finance page. Both require password re-authentication. Account
numbers are encrypted as Frappe Password fields and displayed masked in the app.
Finance verifies ownership, classification and supporting evidence before use.
A pending change blocks new releases; processing payments retain their frozen
recipient. Verification/replacement notifies the scout. Finance can reveal the
actual details only after another password check; the view is audited.

## Record a manual payout

1. Create DD Scout Payout with verified beneficiary, one currency, approved
   business channel and allocation rows. Allocate to earning or agreed travel
   advance. Multiple payments can settle one earning; one payment can cover
   multiple arrangements for the same scout/currency.
2. Finance approves and reserves the allocations. If the releaser also approved
   the work, a different Finance/System Manager must independently review the
   final amount, beneficiary, channel and allocations. Changed terms invalidate
   that review. No unreviewed small-team override is provided.
3. Begin processing, then execute the actual transfer in the approved business
   channel. No Frappe or mobile button sends money. Use the payout document name
   as the business reference and preserve the actual provider transaction ID.
4. Reconcile actual success, recipient and amount to bank/mobile-money records.
   Confirm Paid with private confirmation evidence, actual reference and notes.
   The reference has a global unique key to prevent reuse. Only confirmed success
   settles the earning and generates a payment notification.
5. A timeout remains Processing or On hold and keeps its reservation. Verify the
   outcome before retrying externally. Confirm failed only with actual failure
   evidence. A wrong-recipient transfer is a recovery case, not settlement of the
   correct scout. Payment reversals are new bounded records against the original.

An advance reduces the later amount due; it is not an additional expense or an
extra reduction in company margin. Gross approved scout entitlement remains a
cost even if unpaid or subject to withholding. Net payable and currency are
shown separately from estimated arrangements awaiting work approval. Earnings
supports saved per-account snapshots, marked stale/offline; mutations require a
successful online request. It presents no wallet balance or cash withdrawal.

## Company margin and financial decisions

Company margin is net quoted service revenue less recorded costs and confirmed
service-revenue credits. The page shows planned margin separately from margin
after approved costs. These are provisional operating figures, not cash in a
bank account, distributable owner earnings or full statutory accounting profit.
Record overhead costs if they should be included. Never add scout fees again as
DD Finance Cost; use those cost records for logistics, gateway charges, other
operating costs and non-scout rework costs. Pending claims/costs still need review.

DD Finance Case links the existing customer issue, task and cancellation/work
stage, rationale, remedy/financial effect, compensation treatment, handler and
next update. An approved case can pause new checkout/dispatch. It does not stop
money already moving externally. Reconcile late payments manually before closing
the case. Explicit compensation can create an entitlement from an accepted bound
arrangement where none exists, with agreement evidence. Existing earnings use
adjustments; a dispute does not delete them. Earlier evidence and reports remain.
This phase reuses the existing customer issue flow; it does not redesign the
website's question/issue forms or implement external chargeback handling.

## Refunds

DD Customer Refund is one case per original completed DD Payment. Approval is
separate from provider execution and confirmation. Finance records the verified
original payment method and checks current merchant restrictions/prior refunds or
chargebacks in Pesapal before approval. An approved refund is entered externally,
then marked Provider pending with its provider case reference. An acknowledgement
is never treated as completion.

Confirm only after reconciliation of actual amount/recipient with private
evidence and an accounting credit-document reference. Original collection status
remains true; the refund has its own history. Full/partial card refunds and
full-only mobile-money refunds follow the documented API restriction. A partial
mobile-money remedy requires documented provider approval, resolution of original
refund/chargeback exposure and a different independent reviewer. Do not substitute
an informal transfer or casually accept another recipient. Confirmed refunds stop
reuse of the original deposit for new dispatch.

Failed refund cases are retained and require provider review; this implementation
does not automatically resubmit them or create another request against the same
transaction. Bank/M-Pesa automation, automatic reconciliation, statutory credit
document generation and tax calculation are outside this manual phase.

Provider references:
[Pesapal refund request](https://developer.pesapal.com/how-to-integrate/e-commerce/api-30-json/refund-request),
[Pesapal business transfers](https://www.pesapal.com/blog/how-to-transfer-funds-from-pesapal-to-mpesa).
Confirm the actual merchant account arrangements before using a payout channel.

## Staging acceptance before enabling

Follow [production ownership](production-script-ownership.md) and
[native integration](native-integration.md) for normal native deployment. Use a backed-up staging Frappe site, migrate standard
DocTypes/Role/page/workspace and build assets, then enable the flag there only.
Test with separate scout, coordinator and Finance users. Confirm assignment
deposit/accepted-offer gates, same/replacement revisit, work approval, claim
receipts/alternatives, independent review, concurrent reservations, recipient
change during processing, instalments/reversals, cancellation compensation,
uncertain payout, card/mobile refund cases and original evidence/history.
Exercise mobile offline snapshots, account switching and a real private receipt
upload on Android/iOS. Verify the actual Desk dialogs and encrypted Password
field lifecycle on the installed Frappe version. Local unit and TypeScript checks
do not replace these site/device checks. Production activation requires the
owner's feature deployment/activation approval; native handover is already complete.
