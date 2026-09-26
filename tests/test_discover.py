import time

from anvilbook.discover import addons_dir, find_installs, find_savedvariables, flavor_dir, looks_like_addon_code


def make_install(root, flavor='_classic_beta_', account='12345#1', saved_file='Auctionator.lua'):
    saved = root / flavor / 'WTF' / 'Account' / account / 'SavedVariables'
    saved.mkdir(parents=True)
    if saved_file:
        (saved / saved_file).write_text('x')
    return saved


def test_finds_saved_variables_under_a_root(tmp_path):
    saved = make_install(tmp_path / 'World of Warcraft')
    assert find_savedvariables([tmp_path]) == [saved / 'Auctionator.lua']


def test_finds_the_folder_even_before_auctionator_has_saved(tmp_path):
    saved = make_install(tmp_path / 'World of Warcraft', saved_file=None)

    installs = find_installs([tmp_path])

    assert [i.savedvariables for i in installs] == [saved]
    assert installs[0].has_prices is False
    assert installs[0].account == '12345#1'
    assert installs[0].flavor == '_classic_beta_'


def test_finds_installs_nested_a_few_folders_deep(tmp_path):
    deep = tmp_path / 'compatdata' / '123' / 'pfx' / 'drive_c' / 'Program Files (x86)' / 'World of Warcraft'
    saved = make_install(deep)
    assert [i.savedvariables for i in find_installs([tmp_path])] == [saved]


def test_search_stops_at_the_deadline(tmp_path):
    make_install(tmp_path / 'World of Warcraft')
    started = time.monotonic()

    find_installs([tmp_path], deadline=time.monotonic() - 1)

    assert time.monotonic() - started < 1


def test_addon_code_paths_are_recognised(tmp_path):
    assert looks_like_addon_code(tmp_path / '_classic_beta_' / 'Interface' / 'AddOns' / 'Auctionator' /
                                 'Source' / 'Auctionator.lua')
    assert not looks_like_addon_code(tmp_path / 'WTF' / 'Account' / '1#1' / 'SavedVariables' / 'Auctionator.lua')


def test_flavor_and_addons_dir_come_from_the_file_path(tmp_path):
    saved = make_install(tmp_path / 'World of Warcraft') / 'Auctionator.lua'
    assert flavor_dir(saved) == tmp_path / 'World of Warcraft' / '_classic_beta_'
    assert addons_dir(saved) == tmp_path / 'World of Warcraft' / '_classic_beta_' / 'Interface' / 'AddOns'
