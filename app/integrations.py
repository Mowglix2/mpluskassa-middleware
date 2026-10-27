import hashlib
import hmac
import time
from urllib.parse import urlparse
import httpx


def valid_signature(body, signature, secret):
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


class UberClient:
    def __init__(self, config):
        self.config = config
        self._token = None
        self._expiry = 0

    def token(self):
        if self._token and time.time() < self._expiry - 120:
            return self._token
        with httpx.Client(timeout=15) as client:
            res = client.post('https://auth.uber.com/oauth/v2/token', data={
                'client_id': self.config.uber_client_id, 'client_secret': self.config.uber_client_secret,
                'grant_type': 'client_credentials', 'scope': self.config.uber_scopes})
            res.raise_for_status()
            d = res.json()
        self._token = d['access_token']
        self._expiry = time.time() + int(d.get('expires_in', 3600))
        return self._token

    def get_order(self, url):
        p = urlparse(url)
        if p.scheme != 'https' or p.hostname != 'api.uber.com' or not p.path.startswith('/v2/eats/order/'):
            raise ValueError('Untrusted Uber resource_href')
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.get(url, headers={'Authorization': f'Bearer {self.token()}'})
            response.raise_for_status()
            return response.json()

    def decision(self, order_id, accept):
        # Explicit integration points: confirm payload and scopes against merchant's Uber API version.
        endpoint = f'https://api.uber.com/v1/eats/orders/{order_id}/' + ('accept_pos_order' if accept else 'deny_pos_order')
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            r = client.post(endpoint, headers={'Authorization': f'Bearer {self.token()}'}, json={})
            r.raise_for_status()
            return r.json() if r.content else {}


class MplusClient:
    def __init__(self, wsdl, username=None, password=None):
        if not wsdl:
            raise ValueError('MPLUS_WSDL is required')
        from zeep import Client
        from zeep.transports import Transport
        from requests import Session
        session = Session()
        if username and password:
            session.auth = (username, password)
        self.service = Client(wsdl=wsdl, transport=Transport(session=session, timeout=20, operation_timeout=20)).service

    def find(self, ext_order_id):
        return self.service.findOrder(ext_order_id)

    def create(self, payload):
        return self.service.createOrder(order=payload)
