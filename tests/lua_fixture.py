import cbor2


def lua_escape(b: bytes) -> bytes:
    out = bytearray()
    for c in b:
        if c == 0x5C:
            out += b'\\\\'
        elif c == 0x22:
            out += b'\\"'
        elif c == 0x0A:
            out += b'\\n'
        elif c == 0x0D:
            out += b'\\r'
        elif c == 0x00:
            out += b'\\000'
        else:
            out.append(c)
    return bytes(out)


def entry(m, day, available, high=None):
    return {'m': m, 'h': {str(day): high if high is not None else m}, 'a': {str(day): available}, 'l': []}


def savedvariables(realm_data, realm='ClassicBetaPvP', vendor=None, as_table=False):
    lines = [b'AUCTIONATOR_CONFIG = {', b'}', b'AUCTIONATOR_PRICE_DATABASE = {', b'["__dbversion"] = 8,']
    if as_table:
        lines += [b'["' + realm.encode() + b'"] = {', b'},']
    else:
        lines.append(b'["' + realm.encode() + b'"] = "' + lua_escape(cbor2.dumps(realm_data)) + b'",')
    lines += [b'}', b'AUCTIONATOR_VENDOR_PRICE_CACHE = {', b'["__dbversion"] = 1,']
    lines += [f'["{k}"] = {v},'.encode() for k, v in (vendor or {}).items()]
    lines.append(b'}')
    return b'\r\n'.join(lines) + b'\r\n'
