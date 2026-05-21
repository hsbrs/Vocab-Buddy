from django.db import migrations, models


COMMON_PLURALS = {
    'haus': 'Häuser',
    'monat': 'Monate',
    'thema': 'Themen',
    'jahr': 'Jahre',
    'euro': 'Euro',
    'mensch': 'Menschen',
    'kind': 'Kinder',
    'tag': 'Tage',
    'stadt': 'Städte',
    'zeit': 'Zeiten',
    'prozent': 'Prozent',
    'foto': 'Fotos',
    'frau': 'Frauen',
    'woche': 'Wochen',
    'ende': 'Enden',
    'mann': 'Männer',
    'sonntag': 'Sonntage',
    'land': 'Länder',
    'deutschland': 'Deutschland',
    'platz': 'Plätze',
    'minute': 'Minuten',
    'schule': 'Schulen',
    'teil': 'Teile',
    'welt': 'Welten',
    'problem': 'Probleme',
    'beispiel': 'Beispiele',
    'wort': 'Wörter',
    'geld': 'Gelder',
    'stunde': 'Stunden',
    'uhr': 'Uhren',
}


def seed_common_plurals(apps, schema_editor):
    Word = apps.get_model('words', 'Word')
    for word in Word.objects.filter(part_of_speech='noun', plural_form=''):
        text = (word.word or '').strip()
        for prefix in ('der ', 'die ', 'das '):
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break
        plural = COMMON_PLURALS.get(text.lower())
        if plural:
            word.plural_form = plural
            word.save(update_fields=['plural_form'])


class Migration(migrations.Migration):

    dependencies = [
        ('words', '0004_normalize_noun_capitalization'),
    ]

    operations = [
        migrations.AddField(
            model_name='word',
            name='plural_form',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.RunPython(seed_common_plurals, migrations.RunPython.noop),
    ]
