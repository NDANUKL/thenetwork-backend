"""Pure finance calculations: no gateway calls, float arithmetic or assumed tax/FX rates."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fieldpulse.payment_rules import money

CURRENCIES={'KES','USD','GBP','EUR'}
EARNING_STATUSES=('Awaiting work approval','Approved awaiting payment','Processing','Paid','Failed','On hold')
RESERVED={'Approved','Processing','On hold'}


def currency(value):
    if value not in CURRENCIES: raise ValueError('Choose an enabled currency: KES, USD, GBP or EUR')
    return value


def positive(value):
    result=money(value)
    if result<=0: raise ValueError('Enter an amount greater than zero')
    return result


def conversion(amount,source,target,rate=None,rate_date=None):
    currency(source);currency(target)
    if source==target: return money(amount)
    if not rate_date: raise ValueError('Record the conversion-rate date; currencies cannot be added together')
    try:
        factor=Decimal(str(rate))
        if not factor.is_finite() or factor<=0: raise ValueError()
    except (InvalidOperation,TypeError,ValueError): raise ValueError('Record a positive agreed/accounting conversion rate') from None
    return money(money(amount)*factor)


def earning_position(offer,earning,expenses=(),adjustments=(),allocations=()):
    """Advances and ordinary instalments settle entitlement; neither is a new cost."""
    approved=bool(earning)
    travel=money(earning['travel_entitlement']) if earning and earning.get('travel_entitlement') is not None else money(offer.get('travel_amount') or 0) if offer.get('travel_basis')=='Fixed allowance' else money(0)
    expenses_total=money(0)
    for expense in expenses:
        if expense.get('status')!='Approved': continue
        if expense.get('currency')!=offer['currency']: raise ValueError('Expense currency must match the accepted scout offer')
        if expense.get('kind')=='Travel':
            if offer.get('travel_basis')!='Reimburse approved actuals': raise ValueError('Do not reimburse travel already covered by a fixed allowance')
            travel+=money(expense['amount'])
        else: expenses_total+=money(expense['amount'])
    if offer.get('travel_basis')=='Reimburse approved actuals' and travel>money(offer.get('travel_amount') or 0): raise ValueError('Approved travel exceeds the accepted cap; agree revised compensation first')
    addition=deduction=money(0)
    for adjustment in adjustments:
        if adjustment.get('status')!='Approved': continue
        if adjustment['currency']!=offer['currency']: raise ValueError('Adjustment currency mismatch')
        sign=-1 if adjustment.get('reversal_of') else 1
        if adjustment['kind']=='Addition': addition+=sign*money(adjustment['amount'])
        else: deduction+=sign*money(adjustment['amount'])
    if addition<0 or deduction<0: raise ValueError('Adjustment reversals exceed the original adjustment')
    fee=money(earning['base_fee']) if earning and earning.get('base_fee') is not None else money(offer['fee'])
    agreed_gross=fee+travel+expenses_total+addition
    if deduction>agreed_gross: raise ValueError('Deductions cannot exceed gross entitlement')
    gross=agreed_gross if approved else money(0)
    advances=paid=reserved_advance=reserved_earning=money(0)
    states=[]
    for allocation in allocations:
        if allocation['currency']!=offer['currency']: raise ValueError('Payout currency mismatch')
        amount=money(allocation['amount']);state=allocation['status'];states.append(state)
        if state=='Paid':
            amount*= -1 if allocation.get('reversal_of') else 1
            if allocation['kind']=='Travel advance': advances+=amount
            else: paid+=amount
        elif state in RESERVED and not allocation.get('reversal_of'):
            if allocation['kind']=='Travel advance': reserved_advance+=amount
            else: reserved_earning+=amount
    if advances<0 or paid<0: raise ValueError('Payment reversals exceed confirmed allocations')
    net=agreed_gross-deduction-advances-paid if approved else money(0)
    if net<0: raise ValueError('Confirmed payments exceed entitlement; record and review the overpayment')
    if earning and earning.get('on_hold'): status='On hold'
    elif 'On hold' in states: status='On hold'
    elif not approved: status='Awaiting work approval'
    elif net==0: status='Paid'
    elif reserved_earning>0 or 'Processing' in states: status='Processing'
    elif states and states[-1]=='Failed': status='Failed'
    else: status='Approved awaiting payment'
    return dict(currency=offer['currency'],agreed_fee=money(offer['fee']),approved_fee=fee if approved else money(0),approved_travel=travel,
        approved_expenses=expenses_total,additions=addition,gross_entitlement=gross,
        estimated_gross=agreed_gross,deductions=deduction,advances_paid=advances,
        earning_payments=paid,net_payable=net,reserved=reserved_earning+reserved_advance,
        available=max(money(0),net-reserved_earning-reserved_advance),
        advance_available=max(money(0),money(offer.get('advance_limit') or 0)-advances-reserved_advance),status=status)


def refund_allowed(payment,amount,method,route='Pesapal',alternative_approved=False):
    amount=positive(amount)
    if payment.get('status')!='Paid': raise ValueError('Refund only a verified completed payment')
    if amount>money(payment['amount']): raise ValueError('Refund exceeds the original collected amount')
    if route=='Pesapal':
        if method not in {'Card','Mobile money'}: raise ValueError('Verify the original payment method with Pesapal')
        if method=='Mobile money' and amount!=money(payment['amount']): raise ValueError('Pesapal documents full-only mobile-payment refunds; obtain an approved alternative before a partial remedy')
    elif route!='Provider-approved alternative' or not alternative_approved:
        raise ValueError('An exceptional repayment route needs documented provider approval and independent review')
    return amount


def margin(revenue,planned,actual,service_refunds=0):
    # Gross supplier entitlement is a cost, even while unpaid. Withholding and
    # advances do not manufacture profit. VAT is excluded from service revenue.
    return dict(net_service_revenue=money(revenue),planned_cost=money(planned),
        approved_cost=money(actual),confirmed_service_refunds=money(service_refunds),
        planned_margin=money(revenue)-money(planned),
        margin_after_approved_costs=money(revenue)-money(service_refunds)-money(actual))
