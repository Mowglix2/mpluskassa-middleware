import json
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.responses import Response
from app.config import Settings
from app.core import PLUMapper, transform_uber_eats_to_mplus, MappingError
from app.db import Store
from app.integrations import valid_signature
from app.service import OrderService

settings = Settings()
store = Store(settings.db_path)
service = OrderService(settings, store)
app = FastAPI(title='Uber Eats → MplusKASSA middleware (reconstructed)', version='0.1.0')


def admin(x_admin_token: str | None = Header(default=None)):
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(401, 'Invalid admin token')


@app.get('/health')
def health():
    return {'ok': True, 'mode': 'dry_run' if settings.dry_run else 'live',
            'items': len(service.mapper.items), 'modifiers': len(service.mapper.modifiers)}


@app.post('/webhooks/ubereats')
async def uber_webhook(request: Request, x_uber_signature: str | None = Header(default=None)):
    body = await request.body()
    if not valid_signature(body, x_uber_signature, settings.uber_client_secret):
        raise HTTPException(401, 'Invalid webhook signature')
    try:
        evt = json.loads(body)
        if evt.get('event_type') == 'orders.notification':
            if settings.uber_store_id and evt['meta']['user_id'] != settings.uber_store_id:
                raise HTTPException(403, 'Unknown store')
            store.ingest(evt)
        elif evt.get('event_type') in ('orders.cancel', 'orders.failure'):
            oid = str(evt.get('meta', {}).get('resource_id',''))
            current = store.get(oid)
            if current:
                store.update(oid, 'cancel_notice')
        # Other events accepted but ignored intentionally.
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, 'Invalid event')
    return Response(status_code=200, content=b'')


@app.get('/orders', dependencies=[Depends(admin)])
def orders():
    return store.list()


@app.get('/orders/{order_id}', dependencies=[Depends(admin)])
def order(order_id: str):
    found = store.get(order_id)
    if not found:
        raise HTTPException(404)
    return found


@app.post('/simulate', dependencies=[Depends(admin)])
async def simulate(request: Request):
    """Offline mapping preview. Never submits to Mplus or Uber."""
    raw = await request.json()
    try:
        return transform_uber_eats_to_mplus(raw, service.mapper,
            branch=settings.mplus_branch, relation=settings.mplus_relation,
            employee=settings.mplus_employee, vat_code=settings.mplus_vat_code,
            vat_method=settings.mplus_vat_method,
            delivery_method=settings.mplus_delivery_method or None)
    except MappingError as exc:
        raise HTTPException(422, str(exc))
