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