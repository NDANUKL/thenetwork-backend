"""Session caps, MFA challenge boundaries and activation policy."""
from contextlib import nullcontext
from datetime import datetime, timedelta
import types
import unittest
from unittest.mock import MagicMock, patch
from test_native_integration import fake_frappe, load

class ScoutSessionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, 12)
        self.f = fake_frappe()
        self.f.AuthenticationError = PermissionError
        self.f.flags = types.SimpleNamespace(dd_verified_mfa_user=None)
        self.f.session.user = 'scout@example.test'
        self.f.db.exists.return_value = 'SCOUT'
        self.f.local.session_obj.data = {'sid': 'real-session', 'data': {'creation': self.now.isoformat()}}
        self.utils = types.SimpleNamespace(now_datetime=lambda:self.now,get_datetime=datetime.fromisoformat)
        self.module = load('scout_session_test', 'fieldpulse/scout_sessions.py', {'frappe':self.f,'frappe.utils':self.utils})

    def validate(self, mfa=False):
        with patch.dict('sys.modules', {'frappe.twofactor':types.SimpleNamespace(should_run_2fa=lambda user:mfa)}):
            self.module.validate_session(self.f.session.user)

    def test_absolute_expiry_cannot_be_renewed_by_recent_activity(self):
        payload=self.f.local.session_obj.data['data']
        payload['creation']=(self.now-timedelta(days=7)).isoformat()
        payload['last_updated']=self.now.isoformat()
        with self.assertRaises(PermissionError):self.validate()
        payload['creation']=(self.now-timedelta(days=7,seconds=-1)).isoformat()
        self.validate()

    def test_missing_malformed_future_sessions_and_api_tokens_fail_closed(self):
        for payload in ({},{'creation':'bad'},{'creation':(self.now+timedelta(minutes=10)).isoformat()}):
            self.f.local.session_obj.data={'sid':'sid','data':payload}
            with self.subTest(payload=payload),self.assertRaises(PermissionError):self.validate()
        self.f.local.session_obj.data={'sid':'Guest','data':{'creation':self.now.isoformat()}}
        with self.assertRaises(PermissionError):self.validate()

    def test_mfa_marker_is_required_after_activation(self):
        with self.assertRaises(PermissionError):self.validate(mfa=True)
        self.f.local.session_obj.data['data']['dd_scout_mfa_verified']=True
        self.validate(mfa=True)

    def test_non_scouts_and_guest_are_unchanged(self):
        self.f.db.exists.return_value=None
        self.validate(mfa=True)
        self.module.validate_session('Guest')
        self.module.validate_session('Administrator')

    def test_other_login_routes_cannot_bypass_scout_second_factor(self):
        with patch.dict('sys.modules',{'frappe.twofactor':types.SimpleNamespace(should_run_2fa=lambda user:True)}):
            with self.assertRaises(PermissionError):self.module.require_verified_login(self.f.session.user)
            self.f.flags.dd_verified_mfa_user=self.f.session.user
            self.module.require_verified_login(self.f.session.user)

    def test_new_session_marks_only_server_verified_mfa(self):
        payload={}
        self.f.local.session_obj.data=types.SimpleNamespace(data=payload)
        self.module.session_created(types.SimpleNamespace(user=self.f.session.user))
        self.assertFalse(payload['dd_scout_mfa_verified'])
        self.f.flags.dd_verified_mfa_user=self.f.session.user
        self.module.session_created(types.SimpleNamespace(user=self.f.session.user))
        self.assertTrue(payload['dd_scout_mfa_verified'])
        self.assertEqual(payload['dd_scout_started_at'],self.now.isoformat())

    def test_expired_session_does_not_block_key_based_password_recovery(self):
        self.f.local.session_obj.data={'sid':'old','data':{'creation':'2020-01-01T00:00:00'}}
        self.f.local.request=types.SimpleNamespace(path='/update-password',method='GET')
        self.validate(mfa=True)
        self.f.local.request=types.SimpleNamespace(path='/api/method/frappe.core.doctype.user.user.update_password',method='POST')
        self.f.form_dict={'key':'framework-validates-this-key'}
        self.validate(mfa=True)
        self.f.form_dict={}
        with self.assertRaises(PermissionError):self.validate(mfa=True)

    def test_configuration_has_stronger_throttle_and_email_mfa(self):
        settings=types.SimpleNamespace(enable_two_factor_auth=0,two_factor_method=None,save=MagicMock())
        self.f.get_single.return_value=settings
        role=types.SimpleNamespace(save=MagicMock())
        self.f.get_doc.return_value=role
        result=self.module.configure_security(True)
        self.assertEqual((settings.allow_consecutive_login_attempts,settings.allow_login_after_fail),(5,300))
        self.assertEqual(settings.two_factor_method,'Email')
        self.assertEqual(role.two_factor_auth,1)
        self.assertEqual(result['absolute_scout_session_seconds'],604800)

class MobileTwoFactorTests(unittest.TestCase):
    def setUp(self):
        self.f=fake_frappe();self.f.AuthenticationError=PermissionError
        self.f.form_dict={};self.f.flags=types.SimpleNamespace(dd_verified_mfa_user=None)
        self.f.local.response={};self.f.session.user='Guest'
        self.f.session.sid='new-session';self.f.db.exists.return_value='SCOUT'
        self.code='123456';self.password='correct-password';self.user='scout@example.test';self.required=True
        self.cached_user=self.user;self.cached_password=self.password;self.posted=0;self.deleted=[]
        self.f.cache.return_value.lock.return_value=nullcontext()
        self.f.cache.return_value.delete_value.side_effect=lambda key:self.deleted.append(key)
        outer=self
        class FrameworkLoginManager:
            def login(self):
                if outer.f.form_dict.get('tmp_id'):
                    if outer.f.form_dict.get('otp')!=outer.code:raise PermissionError('Incorrect code')
                elif outer.f.form_dict.get('pwd')!=outer.password:raise PermissionError('Incorrect password')
                elif outer.required:
                    outer.f.local.response.update(verification={'method':'Email'},tmp_id='challenge-123')
                    return False
                self.user=outer.user
                self.post_login()
            def post_login(self,*args,**kwargs):
                outer.posted+=1
                outer.f.session.user=self.user
                outer.verified=outer.f.flags.dd_verified_mfa_user
        self.f.auth.LoginManager=FrameworkLoginManager
        self.two=types.SimpleNamespace(get_cached_user_pass=lambda:(self.cached_user,self.cached_password),should_run_2fa=lambda user:self.required)
        self.utils=types.SimpleNamespace(get_url=lambda:'https://example.test',validate_email_address=lambda value,**kw:value,now_datetime=lambda:'now')
        self.module=load('mobile_mfa_test','fieldpulse/auth.py',{'frappe':self.f,'frappe.utils':self.utils,'frappe.rate_limiter':types.SimpleNamespace(rate_limit=lambda **kw:lambda fn:fn)})

    def login(self,**args):
        with patch.dict('sys.modules',{'frappe.twofactor':self.two,'frappe.utils':self.utils}):
            return self.module._login(self.user,**args)

    def test_password_only_returns_challenge_without_session_or_activity_write(self):
        result=self.login(password=self.password)
        self.assertTrue(result['two_factor_required']);self.assertNotIn('sid',result)
        self.assertEqual(self.posted,0);self.f.db.set_value.assert_not_called()
        self.assertNotIn('pwd',self.f.form_dict)

    def test_code_issues_session_only_after_verification_and_consumes_challenge(self):
        result=self.login(otp=self.code,tmp_id='challenge-123')
        self.assertEqual(result['sid'],'new-session');self.assertEqual(self.verified,self.user)
        self.assertEqual(len(self.deleted),4);self.assertIsNone(self.f.flags.dd_verified_mfa_user)
        self.f.db.set_value.assert_called_once()

    def test_wrong_code_cross_account_and_expired_challenges_never_create_session(self):
        with self.assertRaises(PermissionError):self.login(otp='654321',tmp_id='challenge-123')
        self.cached_user='other@example.test'
        with self.assertRaises(PermissionError):self.login(otp=self.code,tmp_id='challenge-123')
        self.cached_user=self.user;self.cached_password=None
        with self.assertRaises(PermissionError):self.login(otp=self.code,tmp_id='challenge-123')
        self.assertEqual(self.posted,0);self.assertFalse(self.deleted)

    def test_non_mfa_existing_login_remains_compatible_until_activation(self):
        self.required=False
        result=self.login(password=self.password)
        self.assertEqual(result['sid'],'new-session');self.assertEqual(self.posted,1)

    def test_bad_password_and_invalid_code_stop_before_session_creation(self):
        for args in ({'password':'wrong'},{'otp':'123','tmp_id':'challenge-123'},{'otp':self.code,'tmp_id':'short'}):
            with self.subTest(args=args),self.assertRaises(PermissionError):self.login(**args)
        self.assertEqual(self.posted,0)

    def test_auth_request_fields_are_scrubbed_after_success_and_failure(self):
        self.login(otp=self.code,tmp_id='challenge-123')
        for field in ('otp','tmp_id','password','pwd'):self.assertNotIn(field,self.f.form_dict)
        self.f.session.user='Guest'
        with self.assertRaises(PermissionError):self.login(otp='654321',tmp_id='challenge-123')
        for field in ('otp','tmp_id','password','pwd'):self.assertNotIn(field,self.f.form_dict)

    def test_reset_non_scout_user_is_skipped_without_mail(self):
        self.f.db.exists.side_effect=lambda doctype, filters: doctype == 'User'
        result=self.module.request_password_reset(self.user)
        self.assertIn('Scout Profile',result['message'])
        self.f.db.exists.assert_called_once_with('Scout Profile',{'user':self.user})
        self.f.get_doc.assert_not_called()
        self.f.sendmail.assert_not_called()

    def test_profile_membership_is_only_recovery_eligibility_check(self):
        self.f.db.exists.side_effect=lambda doctype, filters: doctype == 'Scout Profile'
        user=types.SimpleNamespace(enabled=False,full_name='Scout',
            _reset_password=MagicMock(return_value='https://example.test/update-password?key=private'))
        self.f.get_doc.return_value=user
        access=types.SimpleNamespace(check_access=MagicMock(side_effect=PermissionError('disabled')))
        with patch.dict('sys.modules',{'fieldpulse.scout_access':access}):
            result=self.module.request_password_reset(' SCOUT@EXAMPLE.TEST ')
        self.f.db.exists.assert_called_once_with('Scout Profile',{'user':self.user})
        access.check_access.assert_not_called()
        self.f.db.get_value.assert_not_called()
        self.f.sendmail.assert_called_once()
        user._reset_password.assert_called_once_with(send_email=False)
        self.assertFalse(user.enabled)
        self.assertNotIn('private',str(result))

    def test_mail_failure_is_not_reported_as_success(self):
        user=MagicMock(full_name='Scout')
        user._reset_password.return_value='https://example.test/update-password?key=private'
        self.f.get_doc.return_value=user
        self.f.sendmail.side_effect=RuntimeError('Mail transport failed')
        with self.assertRaisesRegex(RuntimeError,'Mail transport failed'):
            self.module.request_password_reset(self.user)
        self.f.db.commit.assert_not_called()

    def test_active_reset_returns_generic_reply_and_uses_native_one_time_link(self):
        user=MagicMock(enabled=True,full_name='Scout')
        user._reset_password.return_value='https://example.test/update-password?key=private'
        self.f.get_doc.return_value=user
        access=types.SimpleNamespace(check_access=lambda email:None)
        with patch.dict('sys.modules',{'fieldpulse.scout_access':access}):result=self.module.request_password_reset(self.user)
        self.assertNotIn('private',str(result));user._reset_password.assert_called_once_with(send_email=False)
        self.assertEqual(self.f.sendmail.call_args.kwargs['subject'],'Reset your Ground Scouts password')


class PasswordResetTemplateTests(unittest.TestCase):
    setUp = MobileTwoFactorTests.setUp
    def test_reset_renders_installed_template_before_sending(self):
        from pathlib import Path
        from jinja2 import Environment, FileSystemLoader
        root=Path(__file__).parents[1]
        env=Environment(loader=FileSystemLoader(str(root)))
        self.f.render_template.side_effect=lambda template, context: env.get_template(template).render(context)
        user=types.SimpleNamespace(enabled=True,full_name='Scout',
            _reset_password=lambda **kwargs:'https://example.test/update-password?key=private')
        self.f.get_doc.return_value=user
        access=types.SimpleNamespace(check_access=lambda email:None)
        with patch.dict('sys.modules',{'fieldpulse.scout_access':access}):
            result=self.module.request_password_reset(self.user)
        html=self.f.sendmail.call_args.kwargs['message']
        self.assertIn('https://example.test/update-password?key=private',html)
        self.assertIn('Reset your password',html)
        self.assertNotIn('private',str(result))
