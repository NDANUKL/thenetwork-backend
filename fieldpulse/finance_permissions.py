from fieldpulse.finance_documents import query_condition

def budget(user=None):return query_condition(user,'DD Task Budget')
def offer(user=None):return query_condition(user,'DD Scout Offer')
def expense(user=None):return query_condition(user,'DD Scout Expense')
def earning(user=None):return query_condition(user,'DD Scout Earning')
def adjustment(user=None):return query_condition(user,'DD Earning Adjustment')
def beneficiary(user=None):return query_condition(user,'DD Payout Beneficiary')
def payout(user=None):return query_condition(user,'DD Scout Payout')
def cost(user=None):return query_condition(user,'DD Finance Cost')
def refund(user=None):return query_condition(user,'DD Customer Refund')
def case(user=None):return query_condition(user,'DD Finance Case')
def audit(user=None):return query_condition(user,'DD Finance Audit')
