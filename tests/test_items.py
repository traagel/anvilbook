import json

from anvilbook.items import load_items


def test_load_items_keeps_needed_fields(tmp_path):
    cache = tmp_path / 'items.json'
    cache.write_text(json.dumps([
        {'itemId': 2841, 'name': 'Bronze Bar', 'tooltip': [{'label': 'x'}], 'sellPrice': 50,
         'itemLevel': 25, 'class': 'Trade Goods', 'createdBy': [{'amount': [2, 2]}]},
    ]))
    items = load_items(cache)
    assert list(items) == [2841]
    assert items[2841]['name'] == 'Bronze Bar'
    assert (items[2841]['itemLevel'], items[2841]['class']) == (25, 'Trade Goods')
    assert 'tooltip' not in items[2841]
    assert items[2841]['vendorPrice'] is None
