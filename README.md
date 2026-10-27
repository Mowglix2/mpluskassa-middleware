# Uber Eats → MplusKASSA (functional reconstruction)

This is a **new implementation**, not a recovered original repository. It includes the **original** `plu_mapping.json` recovered from the WhatsApp archive (43 items and 39 modifiers). The historical mapping keys are **names**, not Uber item IDs, so matching is exact after case/diacritic/punctuation normalization; unknown products are blocked.

## Quick start (dry run)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set ADMIN_TOKEN to a long random string in .env
pytest -q
uvicorn app.main:app --reload
# separate terminal, same environment:
python -m app.worker
```

Preview the original mapping with a sample order, without touching either provider:

```bash
curl -s -X POST http://localhost:8000/simulate \
  -H 'X-Admin-Token: YOUR_ADMIN_TOKEN' \
  -H 'Content-Type: application/json' \
  --data-binary @samples/order.json
```

`GET /health`, `GET /orders`, `GET /orders/{order_id}`, `POST /simulate`, and `POST /webhooks/ubereats` are available. Admin endpoints require `X-Admin-Token`; webhook requires Uber's HMAC SHA256 signature. Keep the server behind HTTPS and an access-controlled proxy.

## Workflow

1. Uber sends `orders.notification` with `X-Uber-Signature`.
2. FastAPI verifies raw-body HMAC, saves the event and unique order id in SQLite, and immediately responds 200 with empty body.
3. Worker fetches Uber order through OAuth, maps **all** items and selected modifiers, validates integer-cent prices, then produces an Mplus `createOrder` payload.
4. Default `DRY_RUN=true` means the mapping is persisted for inspection, but **no actual POS write or Uber accept** occurs.
5. In live mode, first look up `findOrder(extOrderId)` then call `createOrder`. An uncertain result is flagged for manual reconciliation and never automatically retried.
6. Uber accept is off by default; only enable once the merchant's version-specific API requests and response bodies have been validated.

## Integration caveats (important)

- This is an **MVP**, not production certified. There is no automatic reconciliation, no cancel propagation, no refunds, no multi-tenant mapping, and no admin UI. The worker is a single process; avoid running two workers against a shared SQLite DB and do not run it without a durable persistent volume.
- Uber order JSON fields differ by version. The parser supports selected common shapes, but **must be adapted and tested using a sanitized real Uber order JSON sample** before live orders. See `_price` and `_selections` in `app/core.py`.
- Monetary values must be confirmed as **integer cents** in the supplied Uber order version. `price` is treated as *unit* price, not line total; discounts/taxes/fees/delivery are not carried across. Do **not** activate live mode before confirming these details.
- For `createOrder`, ensure relation, employee, branch, VAT method, VAT code and delivery method exist in your particular Mplus instance. In contrast to our historical test using VAT-METHOD-EXCLUSIVE, this version defaults to INCLUSIVE. Confirm with accounting/Mplus before activation.
- WSDL-auth differs per Mplus server; HTTP basic is provided as one option and may need an alternative per the assigned API credentials. WSDL must be configured with `MPLUS_WSDL`; no fake URL is supplied.
- `findOrder` existence-check isn't enough for exactly-once across network partitions; if SOAP write times out, check the external ID manually. Never blind retry.
- The Uber accept/deny integration depends on store provisioning, app scopes, API version and merchant permissions. An opt-in implementation exists for accept, but **is untested**; deny is not automatically invoked. Uber requires accept or deny within **11.5 minutes** of notification, so dry-run or manual review alone does not meet their live order SLA.
- For safety, webhook cancellation only records a notice; manual POS cancellation and refund flows are needed.
- Beware of exposing customer data in API admin JSON responses. Use secure storage, least privilege, and limit retention. Never place real secrets in version control.

## Reference documentation

- https://developer.uber.com/docs/eats/guides/webhooks
- https://developer.uber.com/docs/eats/guides/authentication
- https://developers.mpluskassa.nl/tutorials/orders/
- https://developers.mpluskassa.nl/mplus-api/
