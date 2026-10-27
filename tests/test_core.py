from pathlib import Path
import json
import pytest
from app.core import PLUMapper, MappingError, transform_uber_eats_to_mplus
from app.integrations import valid_signature
import hashlib, hmac

mapper = PLUMapper.load('data/plu_mapping.json')

def transform(payload):
    return transform_uber_eats_to_mplus(payload, mapper, branch=1, relation=1, employee=1, vat_code=2)

def test_original_mapping_counts():
    assert len(mapper.items) == 43
    assert len(mapper.modifiers) == 39
    assert mapper.resolve('Schotel köfte', 'item') == 100570
    assert mapper.resolve('cheddar', 'modifier') == 100496

def test_transform():
    p = transform(json.loads(Path('samples/order.json').read_text()))
    assert p['extOrderId'] == 'UBEREATS-test-order-001'
    assert [row['articleNumber'] for row in p['lineList']] == [100491,100496,100537]
    assert [row['data']['quantity'] for row in p['lineList']] == [2,2,1]

def test_unmapped_rejected():
    with pytest.raises(MappingError):
        transform({'id':'1','items':[{'title':'Something else','price':100}]})

def test_no_ambiguous_price():
    with pytest.raises(MappingError):
        transform({'id':'1','items':[{'title':'coca cola','price':'2.50'}]})

def test_signature():
    sig = hmac.new(b'secret', b'hello', hashlib.sha256).hexdigest()
    assert valid_signature(b'hello', sig, 'secret')
    assert not valid_signature(b'HELLO',sig,'secret')
