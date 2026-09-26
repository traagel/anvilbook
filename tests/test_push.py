import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from anvilbook.push import PushClient, PushError


class Handler(BaseHTTPRequestHandler):
    calls: list = []
    status = 200
    body = {'token': 'abc', 'username': 'thordak'}

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        payload = json.loads(self.rfile.read(length) or b'{}')
        Handler.calls.append((self.path, payload, self.headers.get('Authorization')))
        self.send_response(Handler.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(Handler.body).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Handler.calls, Handler.status, Handler.body = [], 200, {'token': 'abc', 'username': 'thordak'}
    httpd = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_port}', Handler
    httpd.shutdown()


def test_login_returns_a_token(server):
    url, handler = server
    assert PushClient(url).login('thordak', 'a long password') == 'abc'
    path, payload, _ = handler.calls[0]
    assert path == '/api/login'
    assert payload == {'username': 'thordak', 'password': 'a long password'}


def test_push_scan_sends_prices_with_the_token(server):
    url, handler = server
    handler.body = {'stored': 2}
    client = PushClient(url, token='abc')
    result = client.push_scan('Realm', '2026-09-26T10:00:00+00:00',
                              [{'item_id': 2770, 'min_price': 57, 'available': 4, 'name': 'Copper Ore'}])
    assert result == {'stored': 2}
    path, payload, auth = handler.calls[0]
    assert path == '/api/push/scan'
    assert auth == 'Bearer abc'
    assert payload['realm'] == 'Realm'
    assert payload['prices'][0]['item_id'] == 2770


def test_character_reagents_are_sent_as_a_list(server):
    url, handler = server
    professions = {'Blacksmithing': {'rank': 148, 'maxRank': 150, 'recipes': {
        3490: {'name': 'Deadly Bronze Poniard', 'minMade': 1, 'maxMade': 1, 'difficulty': 'easy',
               'reagents': {1: {'id': 2841, 'count': 4}, 2: {'id': 3466, 'count': 1}}}}}}
    PushClient(url, token='abc').push_character('Realm', 'Thordak', professions, True)
    _, payload, _ = handler.calls[0]
    assert payload['professions'] == {'Blacksmithing': {'rank': 148, 'maxRank': 150}}
    recipe = payload['recipes']['3490']
    assert recipe['profession'] == 'Blacksmithing'
    assert recipe['reagents'] == [{'id': 2841, 'count': 4}, {'id': 3466, 'count': 1}]


def test_server_errors_become_push_errors(server):
    url, handler = server
    handler.status, handler.body = 429, {'detail': 'At most 20 pushes an hour. Try later.'}
    with pytest.raises(PushError, match='20 pushes'):
        PushClient(url, token='abc').push_scan('Realm', '2026-09-26T10:00:00+00:00',
                                               [{'item_id': 1, 'min_price': 1}])


def test_an_unreachable_server_raises_push_error():
    with pytest.raises(PushError):
        PushClient('http://127.0.0.1:1', token='abc').push_scan('Realm', '2026-09-26T10:00:00+00:00',
                                                                [{'item_id': 1, 'min_price': 1}])


def test_plain_http_is_refused_for_anything_but_localhost():
    with pytest.raises(PushError, match='https'):
        PushClient('http://example.com')
