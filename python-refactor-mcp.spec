# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('python_refactor_mcp')
hiddenimports += collect_submodules('jedi')
hiddenimports += collect_submodules('rope')
hiddenimports += collect_submodules('libcst')
hiddenimports += collect_submodules('pydantic')


a = Analysis(
    ['C:\\Code-Repo\\Jedi-Py-MCP\\src\\python_refactor_mcp\\__main__.py'],
    pathex=['C:\\Code-Repo\\Jedi-Py-MCP\\src'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
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
    name='python-refactor-mcp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='python-refactor-mcp',
)
