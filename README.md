# Sistema Integrado de Gestão de Negócios - Kasa dos Reparos (SIGN-KR)

## Preparação do ambiente

1. Clone do projeto
2. Acessar página do projeto
3. Criar ambiente virtual (python -m venv venv_name)
4. Acessar o ambiente virtual
5. Instalar bibliotecas
6. Executar migrações (migrations)
7. Executar servidor

```
git clone https://github.com/gustavolaires/sign-kr.git
cd sign-kr
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

> `DEBUG` é `False` por padrão (modo app desktop). Para páginas de erro
> detalhadas no desenvolvimento, defina `DJANGO_DEBUG=1` antes do `runserver`.

## Rodar como app desktop (PyWebView)

Abre a aplicação numa janela nativa (sem navegador), servida localmente por
waitress + WhiteNoise — funciona offline com `DEBUG=False`. O `app.py` roda
`migrate` (e `collectstatic` na primeira vez) automaticamente e mantém um perfil
persistente para o carrinho sobreviver ao fechar/reabrir.

```
pip install -r requirements.txt
python manage.py collectstatic --noinput   # popula os estáticos (1ª vez)
python app.py
```

## Instalando pacotes

Instale a biblioteca diretamente e crie o requirements.txt:

```
python -m pip install package
python -m pip freeze > requirements.txt
```

ou 

Adicione a biblioteca em requirements.txt e execute:

```
pip install -r requirements.txt
```

## Atualizando o app desktop após mudanças

O app desktop roda com `DEBUG=False` e o **WhiteNoise serve os estáticos a partir
de `staticfiles/`** (gerado pelo `collectstatic`), e **não** direto do fonte em
`sign/static/`. Por isso, sempre que alterar CSS, JS, imagens ou classes Tailwind,
regenere os estáticos e reabra o app:

1. Rebuild do Tailwind (só se mudou classe usada em template):

```
./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify
```

2. Coletar os estáticos para `staticfiles/`:

```
python manage.py collectstatic --noinput
```

3. Gerar/rodar a nova versão do app:

```
python app.py
```

> Mudanças em Python e em templates HTML aparecem ao reiniciar o `app.py` — só os
> **estáticos** (CSS/JS/imagens) dependem do `collectstatic`.

## Empacotamento com PyInstaller (executável desktop)

Gera um executável distribuível a partir do `app.py`. Usa-se o **modo onedir**
(pasta, **não** arquivo único), configurado em `SIGN-KR.spec` (versionado). O build
resulta em `dist/SIGN-KR/` contendo `SIGN-KR.exe` + a pasta `_internal/`.

O `db.sqlite3` e o `.env` ficam **acessíveis/graváveis** em `_internal/` (que é o
`sys._MEIPASS` do onedir — um diretório real e persistente no disco): o `.env` é
**carregado automaticamente** no boot (via `python-dotenv`) e o `db.sqlite3` é criado
pelo `migrate` na primeira execução. Os `staticfiles` vão embutidos (read-only) e são
servidos pelo WhiteNoise.

**Passos:**

1. Coletar os estáticos (embutidos no bundle):

```
python manage.py collectstatic --noinput
```

2. Gerar o executável a partir do spec versionado:

```
./venv/Scripts/pyinstaller.exe SIGN-KR.spec --noconfirm
```

3. Executar: `dist/SIGN-KR/SIGN-KR.exe`. Na 1ª execução aparecem, em `_internal/`:
   - `db.sqlite3` — criado/atualizado pelo `migrate` (editável, faça backup dele);
   - `.env` — gerado com `DJANGO_DEBUG=0` (edite para configurar; ex.: `DJANGO_DEBUG=1`).

> **Permissão de escrita:** `_internal/` precisa ser gravável para criar o banco.
> Instale o app numa pasta do usuário (ex.: em `%LOCALAPPDATA%`), **não** em
> `C:\Program Files` (protegido para escrita por usuários comuns).

> **Rebuild:** após mudar Python, templates ou estáticos, refaça o `collectstatic`
> e o `pyinstaller` (o `--noconfirm` sobrescreve `build/` e `dist/`). Para depurar
> falhas de runtime do executável, troque `console=False` → `console=True` no
> `SIGN-KR.spec`, rebuilde e rode pelo terminal para ver o traceback.