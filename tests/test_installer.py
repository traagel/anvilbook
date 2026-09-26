import pytest

from anvilbook.installer import ADDON_NAME, addon_source, install_addon, is_installed, target_dir


def savedvariables(tmp_path):
    saved = tmp_path / 'World of Warcraft' / '_classic_beta_' / 'WTF' / 'Account' / '1#1' / 'SavedVariables'
    saved.mkdir(parents=True)
    path = saved / 'Auctionator.lua'
    path.write_text('x')
    return path


def test_addon_ships_with_the_package():
    assert (addon_source() / 'AnvilbookExport.toc').exists()
    assert (addon_source() / 'AnvilbookExport.lua').exists()


def test_install_copies_the_addon_next_to_the_game(tmp_path):
    saved = savedvariables(tmp_path)
    assert not is_installed(saved)

    target = install_addon(saved)

    assert target.name == ADDON_NAME
    assert (target / 'AnvilbookExport.lua').read_text() == (addon_source() / 'AnvilbookExport.lua').read_text()
    assert is_installed(saved)


def test_install_replaces_an_older_copy(tmp_path):
    saved = savedvariables(tmp_path)
    target = install_addon(saved)
    (target / 'AnvilbookExport.lua').write_text('old version')
    (target / 'leftover.lua').write_text('stale file')

    install_addon(saved)

    assert (target / 'AnvilbookExport.lua').read_text() != 'old version'
    assert not (target / 'leftover.lua').exists()


def test_install_keeps_a_symlinked_copy_alone(tmp_path):
    saved = savedvariables(tmp_path)
    target = target_dir(saved)
    target.parent.mkdir(parents=True)
    target.symlink_to(addon_source(), target_is_directory=True)

    with pytest.raises(FileExistsError, match='symlink'):
        install_addon(saved)
