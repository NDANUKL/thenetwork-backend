"""Pure monetary and provider validation rules. All supported currencies use cents."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse


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
