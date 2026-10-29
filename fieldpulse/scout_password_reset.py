"""Complete scout recovery without Frappe's automatic browser login."""
import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import today


@frappe.whitelist(allow_guest=True, methods=['POST'])
@rate_limit(limit=20, seconds=3600)
def update_password(new_password, logout_all_sessions=0, key=None, old_password=None):
    from frappe.core.doctype.user import user as native
    from frappe.utils.password import update_password as store_password

    # Preserve ordinary staff password changes and recovery.
    if not key:
        return native.update_password(new_password, logout_all_sessions, key, old_password)
    result = native._get_user_for_update_password(key, old_password)
    if result.get('message'):
        frappe.local.response.http_status_code = 410
        return result['message']
    user = result.get('user')
    if not user or not frappe.db.exists('Scout Profile', {'user': user}):
        return native.update_password(new_password, logout_all_sessions, key, old_password)

    # Recheck the single-use, expiring token after serializing concurrent resets.
    frappe.db.sql('SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE', [user])
    result = native._get_user_for_update_password(key, old_password)
    if result.get('message') or result.get('user') != user:
        frappe.local.response.http_status_code = 410
        return result.get('message') or 'This reset link is invalid or has already been used.'
    if not isinstance(new_password, str) or not new_password or len(new_password) > native.MAX_PASSWORD_SIZE:
        frappe.throw('Enter a password within the permitted length.')
    user_data = frappe.db.get_value('User', user, ['first_name', 'middle_name', 'last_name', 'email', 'birth_date'])
    strength = native.test_password_strength(new_password, user_data=user_data)
    feedback = strength.get('feedback')
    if feedback and not feedback.get('password_policy_validation_passed', False):
        native.handle_password_test_fail(feedback)
    frappe.get_doc('User', user).validate_reset_password()
    # Consume the token before session revocation; never call login_as().
    frappe.db.set_value('User', user, {'reset_password_key': '', 'redirect_url': '',
                                    'last_password_reset_date': today()})
    store_password(user, new_password, logout_all_sessions=1)
    frappe.cache.hdel('redirect_after_login', user)
    if frappe.session.user == user:
        frappe.local.login_manager.logout()
    return '/scout-password-reset-complete'
