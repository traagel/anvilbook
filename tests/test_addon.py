import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.mark.skipif(not shutil.which('luajit'), reason='luajit not installed')
def test_addon_records_known_recipes():
    res = subprocess.run(
        ['luajit', str(ROOT / 'tests/addon_harness.lua'), str(ROOT / 'addon/AnvilbookExport/AnvilbookExport.lua')],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == 'OK'
