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

## Build do CSS

```
./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify
```