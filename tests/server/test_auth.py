import pytest

from anvilbook.server.auth import (check_password, check_username, hash_password, new_token,
                                   token_hash, verify_password)


def test_password_round_trip():
    stored = hash_password('correct horse battery')
    assert stored.startswith('scrypt$')
    assert verify_password('correct horse battery', stored)
    assert not verify_password('wrong', stored)


def test_same_password_gets_a_different_hash():
    assert hash_password('correct horse battery') != hash_password('correct horse battery')


@pytest.mark.parametrize('stored', ['', 'nonsense', 'scrypt$1$2$3', 'scrypt$a$b$c$d$e'])
def test_broken_hashes_do_not_raise(stored):
    assert verify_password('anything', stored) is False


def test_tokens_are_random_and_only_stored_hashed():
    token, stored = new_token()
    assert len(token) == 64 and token != stored
    assert token_hash(token) == stored
    assert new_token()[0] != token


@pytest.mark.parametrize('name', ['ab', 'x' * 33, 'has space', 'bad/char', ''])
def test_bad_usernames_are_rejected(name):
    with pytest.raises(ValueError):
        check_username(name)


def test_good_username_passes():
    check_username('Thordak_1')


def test_short_passwords_are_rejected():
    with pytest.raises(ValueError):
        check_password('short')
    check_password('long enough password')
