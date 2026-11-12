import datetime as dt
import unittest
from tools.cloudflare_image_backend import CloudflareClient,CloudflareBlocked,MODEL

class UsageSafety(unittest.TestCase):
    def test_invalid_usage_never_clears_gate(self):
        policy=dict(private_direct_api_verified=True,licenses_verified=True,free_hard_cap_verified=True,
                    partner_private_reference_terms_verified=True,verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
        for values in [[-1],[True],[float('nan')],[float('inf')],['0']]:
            def request(method,path,*args):
                if method=='GET':return {'result':[{'name':MODEL}]}
                return {'data':{'viewer':{'accounts':[{'aiInferenceAdaptiveGroups':[{'sum':{'totalNeurons':v}} for v in values]}]}},'errors':None}
            with self.subTest(values=values),self.assertRaisesRegex(CloudflareBlocked,'USAGE_UNKNOWN'):
                CloudflareClient({'safety':policy},request).readiness({'size':[1024,576],'references':[{}]})
    def test_graphql_error_never_clears_gate(self):
        policy=dict(private_direct_api_verified=True,licenses_verified=True,free_hard_cap_verified=True,
                    partner_private_reference_terms_verified=True,verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
        def request(method,path,*args):
            if method=='GET':return {'result':[{'name':MODEL}]}
            return {'data':{'viewer':{'accounts':[{'aiInferenceAdaptiveGroups':[]}]}},'errors':[{'message':'partial'}]}
        with self.assertRaisesRegex(CloudflareBlocked,'USAGE_UNKNOWN'):
            CloudflareClient({'safety':policy},request).readiness({'size':[1024,576],'references':[{}]})
