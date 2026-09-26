from anvilbook.discover import addons_dir, find_savedvariables, flavor_dir


def make_install(root, flavor='_classic_beta_', account='12345#1', addon='Auctionator.lua'):
    saved = root / flavor / 'WTF' / 'Account' / account / 'SavedVariables'
    saved.mkdir(parents=True)
    (saved / addon).write_text('x')
    return saved / addon


def test_finds_saved_variables_under_a_root(tmp_path):
    wanted = make_install(tmp_path / 'World of Warcraft')
    assert find_savedvariables([tmp_path]) == [wanted]


def test_newest_install_comes_first(tmp_path):
    old = make_install(tmp_path / 'old' / 'World of Warcraft', account='1#1')
    new = make_install(tmp_path / 'new' / 'World of Warcraft', account='2#1')
    old.touch()
    new.touch()
    import os
    os.utime(old, (1, 1))
    assert find_savedvariables([tmp_path])[0] == new


def test_ignores_folders_without_auctionator(tmp_path):
    make_install(tmp_path / 'World of Warcraft', addon='Other.lua')
    assert find_savedvariables([tmp_path]) == []


def test_flavor_and_addons_dir_come_from_the_file_path(tmp_path):
    saved = make_install(tmp_path / 'World of Warcraft')
    assert flavor_dir(saved) == tmp_path / 'World of Warcraft' / '_classic_beta_'
    assert addons_dir(saved) == tmp_path / 'World of Warcraft' / '_classic_beta_' / 'Interface' / 'AddOns'
