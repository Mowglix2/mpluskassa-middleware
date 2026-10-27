"""Pure transformation: fail closed if a menu entry is not mapped."""
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


def normalize(s: str) -> str:
    s = unicodedata.normalize('NFKD', str(s)).casefold()
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s).split())


class MappingError(ValueError):
    pass


@dataclass
class PLUMapper:
    items: dict
    modifiers: dict

    @classmethod
    def load(cls, path):
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        if set(raw) != {'items', 'modifiers'}:
            raise MappingError('Expected items and modifiers')
        return cls(**{k: {normalize(name): int(plu) for name, plu in raw[k].items()} for k in ('items','modifiers')})

    def resolve(self, name, kind):
        catalog = self.items if kind == 'item' else self.modifiers
        key = normalize(name)
        if key not in catalog:
            raise MappingError(f'Unmapped {kind}: {name!r}')
        return catalog[key]


def _name(obj):
    val = obj.get('title') or obj.get('name')
    if isinstance(val, dict):
        val = val.get('translations', {}).get('en') or val.get('translations', {}).get('nl') or val.get('default')
    if not isinstance(val, str) or not val.strip():
        raise MappingError(f'Cannot extract name: {obj!r}')
    return val


def _price(value):
    """Only trust documented integer cents; reject ambiguous price structures."""
    if value is None:
        raise MappingError('Missing price; no implicit zero prices allowed')
    if isinstance(value, dict):
        if 'amount' in value:
            value = value['amount']
        elif 'total' in value:
            value = value['total']
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MappingError(f'Expected nonnegative integer cents: {value!r}')
    return value


def _selections(item):
    """Handles a few witnessed/common shapes; others must be adapted using real order fixtures."""
    groups = item.get('selected_modifier_groups') or item.get('selected_modifiers') or item.get('modifiers') or []
    if isinstance(groups, dict):
        groups = list(groups.values())
    selections = []
    for group in groups:
        if not isinstance(group, dict):
            raise MappingError('Unknown modifier representation')
        nested = group.get('selected_items') or group.get('selected_options') or group.get('options')
        if nested is None:
            selections.append(group)
        elif isinstance(nested, list):
            selections.extend(nested)
        else:
            raise MappingError('Unknown nested modifiers')
    return selections


def transform_uber_eats_to_mplus(order, mapper: PLUMapper, *, branch, relation, employee, vat_code,
                                 vat_method='VAT-METHOD-INCLUSIVE', delivery_method=None):
    oid = order.get('id') or order.get('order_id')
    if not oid:
        raise MappingError('Missing order id')
    items = order.get('cart', {}).get('items') if isinstance(order.get('cart'), dict) else None
    if items is None:
        items = order.get('items')
    if not isinstance(items, list) or not items:
        raise MappingError('Missing cart.items or items')
    lines = []
    for item in items:
        if not isinstance(item, dict):
            raise MappingError('Invalid cart item')
        name = _name(item)
        quantity = item.get('quantity', 1)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise MappingError('Invalid quantity')
        price = _price(item.get('price', item.get('unit_price')))
        lines.append({'articleNumber': mapper.resolve(name, 'item'),
                      'data': {'quantity': quantity, 'price': price, 'vatCode': vat_code}, 'text': name})
        for modifier in _selections(item):
            mname = _name(modifier)
            qty = modifier.get('quantity', 1)
            if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
                raise MappingError('Invalid modifier quantity')
            mprice = _price(modifier.get('price', modifier.get('unit_price')))
            lines.append({'articleNumber': mapper.resolve(mname, 'modifier'),
                          'data': {'quantity': quantity * qty, 'price': mprice, 'vatCode': vat_code},
                          'text': f'{name} → {mname}'})
    payload = {'extOrderId': 'UBEREATS-' + str(oid), 'entryBranchNumber': branch,
               'relationNumber': relation, 'employeeNumber': employee,
               'reference': 'Uber Eats ' + str(oid), 'vatMethod': vat_method, 'lineList': lines}
    if delivery_method:
        payload['deliveryMethod'] = delivery_method
    return payload
