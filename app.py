"""Ponto de entrada do SIGN-KR como aplicativo desktop.

Sobe o Django atrás de um servidor WSGI (waitress) numa thread local e abre a
aplicação numa janela nativa (PyWebView), apontando para http://127.0.0.1.

Os estáticos são servidos pelo WhiteNoise (ver core/settings.py), então o app
funciona offline com DEBUG=False, sem depender do dev-server do Django.
"""

import os
import socket
import sys
import threading
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
from django.conf import settings
from django.core.management import call_command

import waitress
import webview


def prepare_django():
    """Inicializa o Django e garante banco/estáticos prontos (auto-cura)."""
    django.setup()

    # Na primeira execução (ex.: app recém-instalado) o STATIC_ROOT não existe;
    # popula com os estáticos para o WhiteNoise servir.
    if not settings.STATIC_ROOT.exists():
        call_command('collectstatic', '--noinput', verbosity=0)

    # Garante o schema do banco atualizado, sem exigir passos manuais.
    call_command('migrate', '--noinput', verbosity=0)


def pick_free_port():
    """Reserva uma porta livre em 127.0.0.1 para evitar conflitos."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def serve(port):
    """Serve o WSGI do Django com waitress (chamado numa thread daemon)."""
    from core.wsgi import application

    waitress.serve(application, host='127.0.0.1', port=port, threads=8)


def wait_until_ready(port, timeout=15.0):
    """Bloqueia até o servidor aceitar conexões (evita tela de erro inicial)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return True
        time.sleep(0.05)
    return False


def resource_path(*parts):
    """Resolve um recurso empacotado tanto em dev quanto no PyInstaller.

    Quando congelado, o PyInstaller extrai os dados para ``sys._MEIPASS``; em
    execução a partir do fonte, usa-se o diretório deste arquivo.
    """
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def webview_storage_path():
    """Perfil persistente do webview para o cookie do carrinho sobreviver.

    Sem storage_path + private_mode=False o webview roda em modo privado e
    descarta o cookie 'cart' a cada fechamento (ver docs/recursos/carrinho.md).
    """
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    path = os.path.join(base, 'SIGN-KR', 'webview')
    os.makedirs(path, exist_ok=True)
    return path


def main():
    prepare_django()

    port = pick_free_port()
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    wait_until_ready(port)

    webview.create_window(
        'SIGN-KR',
        f'http://127.0.0.1:{port}/',
        maximized=True,
    )
    # Ícone da janela (barra de títulos + barra de tarefas). Requer .ico no
    # backend EdgeChromium do Windows (System.Drawing.Icon não lê PNG).
    icon = resource_path('sign', 'static', 'sign', 'img', 'page_icon.ico')
    webview.start(
        private_mode=False,
        storage_path=webview_storage_path(),
        icon=icon,
    )


if __name__ == '__main__':
    main()
