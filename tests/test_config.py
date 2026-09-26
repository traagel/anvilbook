from anvilbook.config import Config, load_config, write_config


def test_defaults_when_there_is_no_file(tmp_path):
    config = load_config(tmp_path / 'missing.toml')
    assert config == Config(data_dir=None, savedvariables_path=None, host='127.0.0.1', port=8765, open_browser=True)


def test_reads_values_from_the_file(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('savedvariables_path = "/games/wow/Auctionator.lua"\nport = 9000\nopen_browser = false\n')
    config = load_config(path)
    assert str(config.savedvariables_path) == '/games/wow/Auctionator.lua'
    assert (config.port, config.open_browser) == (9000, False)


def test_write_then_read_round_trip(tmp_path):
    path = tmp_path / 'nested' / 'config.toml'
    write_config(path, savedvariables_path='/games/wow/Auctionator.lua')
    assert str(load_config(path).savedvariables_path) == '/games/wow/Auctionator.lua'
    write_config(path, savedvariables_path=None)
    assert load_config(path).savedvariables_path is None


def test_bad_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('this is not toml =')
    assert load_config(path).port == 8765
