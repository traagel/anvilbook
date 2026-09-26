# PyInstaller build: `uv run pyinstaller anvilbook.spec`
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('anvilbook', includes=['static/*', 'addon/**/*'])

a = Analysis(
    ['src/anvilbook/__main__.py'],
    pathex=['src'],
    datas=datas,
    hiddenimports=['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
                   'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='anvilbook',
    console=True,
    upx=False,
)
