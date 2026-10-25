import unittest
from decimal import Decimal
from fieldpulse.finance_rules import earning_position, conversion, refund_allowed, margin


class FinanceRulesTests(unittest.TestCase):
    def setUp(self):
        self.offer=dict(currency='KES',fee='2000',travel_basis='Fixed allowance',travel_amount='500',advance_limit='500')
        self.earning=dict(base_fee='2000',travel_entitlement='500',on_hold=0)

    def payment(self,amount,status='Paid',kind='Earning',**extra):
        return dict(amount=amount,status=status,kind=kind,currency='KES',**extra)

    def test_work_approval_creates_entitlement_without_customer_balance_dependency(self):
        pending=earning_position(self.offer,None)
        self.assertEqual(pending['gross_entitlement'],0)
        self.assertEqual(pending['estimated_gross'],Decimal('2500'))
        self.assertEqual(pending['status'],'Awaiting work approval')
        self.assertEqual(earning_position(self.offer,self.earning)['net_payable'],Decimal('2500'))

    def test_advance_settles_entitlement_but_does_not_reduce_gross_cost(self):
        p=earning_position(self.offer,self.earning,allocations=[self.payment('500',kind='Travel advance')])
        self.assertEqual(p['gross_entitlement'],Decimal('2500'))
        self.assertEqual(p['advances_paid'],Decimal('500'))
        self.assertEqual(p['net_payable'],Decimal('2000'))

    def test_pending_advance_and_payout_cannot_reserve_same_money(self):
        p=earning_position(self.offer,self.earning,allocations=[self.payment('500','Processing','Travel advance'),self.payment('1500','Approved')])
        self.assertEqual(p['available'],Decimal('500'))
        self.assertEqual(p['reserved'],Decimal('2000'))
        self.assertEqual(p['advance_available'],0)

    def test_uncertain_outcome_stays_reserved_and_hold_has_precedence(self):
        for state in ('Processing','On hold'):
            p=earning_position(self.offer,self.earning,allocations=[self.payment('2500',state)])
            self.assertEqual(p['available'],0)
            self.assertEqual(p['net_payable'],Decimal('2500'))
            self.assertEqual(p['status'],state)

    def test_confirmed_failure_releases_reservation(self):
        p=earning_position(self.offer,self.earning,allocations=[self.payment('2500','Failed')])
        self.assertEqual(p['available'],Decimal('2500'))
        self.assertEqual(p['status'],'Failed')

    def test_advance_hold_is_visible_even_before_work_approval(self):
        p=earning_position(self.offer,None,allocations=[self.payment('500','On hold','Travel advance')])
        self.assertEqual(p['status'],'On hold')
        self.assertEqual(p['advance_available'],0)

    def test_multiple_confirmed_allocations_settle_one_earning(self):
        p=earning_position(self.offer,self.earning,allocations=[self.payment('500',kind='Travel advance'),self.payment('1000'),self.payment('1000')])
        self.assertEqual(p['status'],'Paid')
        self.assertEqual(p['net_payable'],0)

    def test_reversal_reopens_amount_due_without_deleting_payment(self):
        p=earning_position(self.offer,self.earning,allocations=[self.payment('2500'),self.payment('400',reversal_of='PAYOUT-1')])
        self.assertEqual(p['net_payable'],Decimal('400'))
        self.assertEqual(p['earning_payments'],Decimal('2100'))

    def test_claims_need_approval_and_cannot_double_fixed_travel(self):
        pending=dict(kind='Expense',status='Submitted',amount='100',currency='KES')
        self.assertEqual(earning_position(self.offer,self.earning,[pending])['approved_expenses'],0)
        with self.assertRaises(ValueError):earning_position(self.offer,self.earning,[dict(pending,status='Approved',kind='Travel')])

    def test_actual_travel_cap_and_currency_enforced(self):
        offer=dict(self.offer,travel_basis='Reimburse approved actuals')
        earning=dict(self.earning,travel_entitlement=0)
        claim=dict(kind='Travel',status='Approved',amount='400',currency='KES')
        self.assertEqual(earning_position(offer,earning,[claim])['approved_travel'],Decimal('400'))
        with self.assertRaises(ValueError):earning_position(offer,earning,[dict(claim,amount='501')])
        with self.assertRaises(ValueError):earning_position(offer,earning,[dict(claim,currency='USD')])

    def test_deduction_is_not_extra_company_margin(self):
        adjustment=dict(kind='Deduction',status='Approved',amount='100',currency='KES')
        p=earning_position(self.offer,self.earning,adjustments=[adjustment])
        self.assertEqual(p['net_payable'],Decimal('2400'))
        self.assertEqual(p['gross_entitlement'],Decimal('2500'))
        self.assertEqual(margin('4000','2500',p['gross_entitlement'])['margin_after_approved_costs'],Decimal('1500'))

    def test_no_assumed_fx_and_negative_margin_preserved(self):
        for rate,date in ((None,None),('0','2026-10-25'),('NaN','2026-10-25')):
            with self.assertRaises(ValueError):conversion('10','USD','KES',rate,date)
        self.assertEqual(conversion('10','USD','KES','130','2026-10-25'),Decimal('1300'))
        self.assertEqual(margin('100','200','150','10')['margin_after_approved_costs'],Decimal('-60'))

    def test_refund_eligibility_method_amount_and_alternative(self):
        payment=dict(status='Paid',amount='1000')
        self.assertEqual(refund_allowed(payment,'200','Card'),Decimal('200'))
        self.assertEqual(refund_allowed(payment,'1000','Mobile money'),Decimal('1000'))
        for amount,method in (('200','Mobile money'),('1001','Card'),('100','Unknown')):
            with self.assertRaises(ValueError):refund_allowed(payment,amount,method)
        with self.assertRaises(ValueError):refund_allowed(dict(payment,status='Pending'),'100','Card')
        with self.assertRaises(ValueError):refund_allowed(payment,'100','Mobile money','Provider-approved alternative')
        self.assertEqual(refund_allowed(payment,'100','Mobile money','Provider-approved alternative',True),Decimal('100'))


if __name__=='__main__':unittest.main()
