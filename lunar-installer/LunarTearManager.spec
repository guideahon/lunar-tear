# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\cristian\\Documents\\lunar-tear\\lunar-installer\\app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\cristian\\Documents\\lunar-tear\\lunar-installer\\dashboard.html', '.'), ('C:\\Users\\cristian\\Documents\\lunar-tear\\lunar-installer\\config.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LunarTearManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\cristian\\Documents\\lunar-tear\\lunar-tear.ico'],
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LunarTearManager',
)
