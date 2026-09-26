import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

TIMEOUT = 20


class PushError(Exception):
    pass


def _reagents(value) -> list[dict]:
    # The game writes reagents as a Lua table, which reads back as a dict keyed 1, 2, 3.
    rows = [value[k] for k in sorted(value)] if isinstance(value, dict) else list(value or [])
    return [{'id': int(r['id']), 'count': int(r['count'])} for r in rows]


class PushClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = (base_url or '').rstrip('/')
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ('http', 'https'):
            raise PushError('The server address must start with https://')
        # Passwords and tokens cross this wire.
        if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1'):
            raise PushError('Use https, or the password would travel in the open')
        self.token = token

    def _call(self, method: str, path: str, body: dict | None = None, retries: int = 1) -> dict:
        request = urllib.request.Request(f'{self.base_url}{path}', method=method,
                                         data=json.dumps(body).encode() if body is not None else None)
        request.add_header('Content-Type', 'application/json')
        if self.token:
            request.add_header('Authorization', f'Bearer {self.token}')
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read() or b'{}')
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                detail = json.loads(e.read() or b'{}').get('detail', '')
            except ValueError:
                pass
            raise PushError(detail or f'The server said {e.code}')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # A push often lands while the game reloads and the link flaps, so try once more.
            if retries > 0:
                return self._call(method, path, body, retries - 1)
            raise PushError(f'Could not reach the server: {e}')

    def register(self, username: str, password: str) -> str:
        self.token = self._call('POST', '/api/register',
                                {'username': username, 'password': password})['token']
        return self.token

    def login(self, username: str, password: str) -> str:
        self.token = self._call('POST', '/api/login',
                                {'username': username, 'password': password})['token']
        return self.token

    def logout(self) -> None:
        self._call('POST', '/api/logout')
        self.token = None

    def push_scan(self, realm: str, taken_at: str, prices: list[dict]) -> dict:
        return self._call('POST', '/api/push/scan',
                          {'realm': realm, 'taken_at': taken_at, 'prices': prices})

    def push_character(self, realm: str, name: str, professions: dict, published: bool) -> dict:
        recipes = {}
        for profession, data in professions.items():
            for item_id, recipe in (data.get('recipes') or {}).items():
                recipes[str(item_id)] = {
                    'name': recipe.get('name'), 'minMade': recipe.get('minMade') or 1,
                    'maxMade': recipe.get('maxMade') or 1, 'difficulty': recipe.get('difficulty'),
                    'profession': profession, 'reagents': _reagents(recipe.get('reagents'))}
        return self._call('POST', '/api/push/character', {
            'realm': realm, 'name': name, 'published': published,
            'professions': {p: {'rank': d.get('rank'), 'maxRank': d.get('maxRank')}
                            for p, d in professions.items()},
            'recipes': recipes})

    def unpublish_character(self, realm: str, name: str) -> dict:
        return self._call('DELETE', f'/api/push/character/{quote(realm)}/{quote(name)}')

    def delete_account(self) -> None:
        self._call('DELETE', '/api/account')
