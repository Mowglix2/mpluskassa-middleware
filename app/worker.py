import logging
import time
from app.config import Settings
from app.db import Store
from app.service import OrderService

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def main():
    config = Settings()
    store = Store(config.db_path)
    service = OrderService(config, store)
    log.info('Worker started (dry_run=%s)', config.dry_run)
    while True:
        oid = store.claim()
        if oid:
            try:
                log.info('Order %s: %s', oid, service.process(oid)['state'])
            except Exception:
                log.exception('Unexpected processing failure for %s', oid)
                store.update(oid, 'worker_error', error='Unexpected worker failure; inspect logs')
        else:
            time.sleep(1)

if __name__ == '__main__':
    main()
