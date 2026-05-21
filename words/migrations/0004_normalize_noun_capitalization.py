from django.db import migrations


def normalize_nouns(apps, schema_editor):
    Word = apps.get_model('words', 'Word')
    for word in Word.objects.filter(part_of_speech='noun'):
        text = (word.word or '').strip()
        for prefix in ('der ', 'die ', 'das '):
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break
        if not text:
            continue
        normalized = text[:1].upper() + text[1:]
        if normalized == word.word:
            continue
        if Word.objects.filter(word__iexact=normalized).exclude(pk=word.pk).exists():
            continue
        word.word = normalized
        word.save(update_fields=['word'])


class Migration(migrations.Migration):

    dependencies = [
        ('words', '0003_word_language_metadata'),
    ]

    operations = [
        migrations.RunPython(normalize_nouns, migrations.RunPython.noop),
    ]
