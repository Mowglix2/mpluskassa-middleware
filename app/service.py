import json
import logging
from app.core import PLUMapper, transform_uber_eats_to_mplus, MappingError
from app.integrations import UberClient, MplusClient

log = logging.getLogger(__name__)

class OrderService:
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.mapper = PLUMapper.load(config.mapping_path)
        self.uber = UberClient(config)

    def process(self, oid):
        row = self.store.get(oid)
        if not row:
            raise KeyError(oid)
        if row['state'] not in ('processing','queued','mapping_error'):
            return row
        try:
            order = self.uber.get_order(row['resource_href']) if not row.get('raw_order') else json.loads(row['raw_order'])
            payload = transform_uber_eats_to_mplus(order, self.mapper,
                branch=self.config.mplus_branch, relation=self.config.mplus_relation,
                employee=self.config.mplus_employee, vat_code=self.config.mplus_vat_code,
                vat_method=self.config.mplus_vat_method,
                delivery_method=self.config.mplus_delivery_method or None)
            self.store.update(oid, 'mapped', raw_order=json.dumps(order), mplus_payload=json.dumps(payload))
        except MappingError as exc:
            self.store.update(oid, 'mapping_error', error=str(exc))
            return self.store.get(oid)
        except Exception as exc:
            self.store.update(oid, 'fetch_error', error=str(exc))
            return self.store.get(oid)
        if self.config.dry_run:
            self.store.update(oid, 'dry_run_complete')
            return self.store.get(oid)
        try:
            mplus = MplusClient(self.config.mplus_wsdl, self.config.mplus_username, self.config.mplus_password)
            ext_id = payload['extOrderId']
            existing = mplus.find(ext_id)
            if existing:
                result = existing
            else:
                result = mplus.create(payload)
            if not result:
                raise RuntimeError('Mplus returned empty/false result')
            self.store.update(oid, 'pos_created', mplus_result=str(result))
        except Exception as exc:
            # No automatic retry on uncertain write; check Mplus findOrder manually before retry.
            self.store.update(oid, 'pos_uncertain', error=str(exc))
            return self.store.get(oid)
        if self.config.auto_accept_uber and self.config.enable_uber_decisions:
            try:
                self.uber.decision(oid, True)
                self.store.update(oid, 'accepted')
            except Exception as exc:
                self.store.update(oid, 'accept_error', error=str(exc))
        return self.store.get(oid)
