import json
import urllib.request
from pathlib import Path

URL = 'https://raw.githubusercontent.com/nexus-devs/wow-classic-items/master/data/json/data.json'
FIELDS = ('name', 'icon', 'quality', 'requiredLevel', 'itemLevel', 'class', 'sellPrice', 'vendorPrice', 'createdBy')


def load_items(cache: Path) -> dict[int, dict]:
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        part = cache.with_suffix('.part')
        urllib.request.urlretrieve(URL, part)
        part.replace(cache)
    return {x['itemId']: {k: x.get(k) for k in FIELDS} for x in json.loads(cache.read_bytes())}
