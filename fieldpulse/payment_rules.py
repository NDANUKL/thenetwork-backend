"""Pure monetary and provider validation rules. All supported currencies use cents."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse


PAYMENT_TERMS = 'Pay 50% upfront; review your approved report before paying the remaining 50%. Scout assignment starts after your deposit is verified.'


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal("1000000000"):
            raise ValueError("Invalid amount")
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid amount") from None


def instalments(total):
    total = money(total)
    if total < Decimal("0.02"):
        raise ValueError("Quotation total must allow two positive payments")
    deposit = money(total / 2)
    return deposit, total - deposit


def checkout_url(value, environment):
    parsed = urlparse(value or "")
    host = "cybqa.pesapal.com" if environment == "sandbox" else "pay.pesapal.com"
    if parsed.scheme != "https" or parsed.netloc != host or parsed.username or parsed.password:
        raise ValueError("Invalid Pesapal checkout address")
    return value


def verified_status(payload, reference, amount, currency):
    if str(payload.get("status")) != "200":
        raise ValueError("Provider verification failed")
    if payload.get("merchant_reference") != reference:
        raise ValueError("Payment reference mismatch")
    if payload.get("currency") != currency or money(payload.get("amount")) != money(amount):
        raise ValueError("Payment amount or currency mismatch")
    statuses = {0: "Pending", 1: "Paid", 2: "Failed", 3: "Reversed"}
    try:
        state = statuses[int(payload["status_code"])]
    except (KeyError, ValueError, TypeError):
        raise ValueError("Unknown provider payment state") from None
    if state == "Paid" and not payload.get("confirmation_code"):
        raise ValueError("Missing payment confirmation")
    return state


def quotation_totals(subtotal, discount_type="None", discount_value=0, vat_rate=16, tax_inclusive=False):
    subtotal = money(subtotal)
    value = money(discount_value or 0)
    rate = money(vat_rate if vat_rate is not None else 16)
    if discount_type not in ("None", "Percentage", "Fixed amount"):
        raise ValueError("Choose a valid discount type")
    if rate > 100 or (discount_type == "Percentage" and value > 100):
        raise ValueError("Percentages must be between 0 and 100")
    if discount_type == "None" and value:
        raise ValueError("Select a discount type before entering a discount")
    discount = money(subtotal * value / 100) if discount_type == "Percentage" else value
    if discount > subtotal:
        raise ValueError("Discount cannot exceed the subtotal")
    discounted = subtotal - discount
    taxable = money(discounted / (1 + rate / 100)) if tax_inclusive else discounted
    vat = discounted - taxable if tax_inclusive else money(taxable * rate / 100)
    total = discounted if tax_inclusive else taxable + vat
    instalments(total)
    return dict(subtotal=subtotal, discount_amount=discount, taxable_amount=taxable, vat_amount=vat, total=total)
