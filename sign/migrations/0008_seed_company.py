from django.db import migrations


def create_company(apps, schema_editor):
    """Cria a empresa singleton genérica (o usuário preenche os dados depois)."""
    Company = apps.get_model("sign", "Company")
    Company.objects.get_or_create(pk=1, defaults={"name": "My Company"})


def delete_company(apps, schema_editor):
    Company = apps.get_model("sign", "Company")
    Company.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sign", "0007_company"),
    ]

    operations = [
        migrations.RunPython(create_company, delete_company),
    ]
