# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o SIGN-KR (app desktop Django + PyWebView).

Modo onedir (não onefile): gera dist/SIGN-KR/SIGN-KR.exe + dist/SIGN-KR/_internal/.
db.sqlite3 e .env são criados/lidos em _internal/ em runtime (gravável, acessível);
os staticfiles são embutidos ali (read-only) e servidos pelo WhiteNoise.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all

# Ao executar o .spec, a raiz do projeto ainda não está no sys.path, então os
# helpers collect_* não conseguiriam importar o pacote `sign` (retornariam vazio
# e os templates/estáticos ficariam de fora). SPECPATH é o diretório do .spec.
sys.path.insert(0, SPECPATH)

# Templates/estáticos do pacote sign (inclui img/page_icon.ico) + estáticos coletados.
datas = collect_data_files('sign')
datas += [('staticfiles', 'staticfiles')]
# Versão do app, acessível em _internal/ em runtime (ao lado de .env/db.sqlite3).
datas += [('version.txt', '.')]

# Código dinâmico do app (migrations, views, context_processors, templatetags).
hiddenimports = collect_submodules('sign')

# tzdata: USE_TZ=True e o Windows não tem o tz database do SO.
tz_datas, tz_binaries, tz_hidden = collect_all('tzdata')
datas += tz_datas
hiddenimports += tz_hidden

# Servidor WSGI, estáticos e backend do webview (pywebview/pythonnet).
hiddenimports += collect_submodules('waitress')
hiddenimports += collect_submodules('whitenoise')
hiddenimports += collect_submodules('webview')
hiddenimports += ['clr']

# Migrations das apps contrib do Django (rodam no migrate ao subir).
for _app in ('admin', 'auth', 'contenttypes', 'sessions', 'messages'):
    hiddenimports += collect_submodules(f'django.contrib.{_app}.migrations')


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=tz_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# O hook oficial do Django (hook-django.py) embute o db.sqlite3 que estiver ao
# lado do manage.py. Não queremos enviar o banco de dev; o migrate cria um novo
# em runtime (em _internal/). Removemos qualquer db.sqlite3 dos datas coletados.
a.datas = [d for d in a.datas if os.path.basename(d[0]).lower() != 'db.sqlite3']

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SIGN-KR',
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
    icon='sign/static/sign/img/page_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SIGN-KR',
)
