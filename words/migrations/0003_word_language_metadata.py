from django.db import migrations, models


def infer_existing_metadata(apps, schema_editor):
    Word = apps.get_model('words', 'Word')
    for word in Word.objects.all():
        text = (word.word or '').strip()
        lower_text = text.lower()
        updates = {}

        if getattr(word, 'is_verb', False):
            updates['part_of_speech'] = 'verb'
        elif lower_text.startswith(('der ', 'die ', 'das ')):
            article = lower_text.split(' ', 1)[0]
            updates['part_of_speech'] = 'noun'
            updates['article'] = article
            updates['gender'] = {
                'der': 'masculine',
                'die': 'feminine',
                'das': 'neuter',
            }.get(article, '')

        if updates:
            for field, value in updates.items():
                setattr(word, field, value)
            word.save(update_fields=list(updates.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ('words', '0002_word_context_paragraph_word_example_sentences_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='word',
            name='article',
            field=models.CharField(blank=True, choices=[('', 'No article'), ('der', 'der'), ('die', 'die'), ('das', 'das'), ('plural', 'plural die')], default='', max_length=10),
        ),
        migrations.AddField(
            model_name='word',
            name='category',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='word',
            name='gender',
            field=models.CharField(blank=True, choices=[('', 'None'), ('masculine', 'Masculine'), ('feminine', 'Feminine'), ('neuter', 'Neuter'), ('plural', 'Plural')], default='', max_length=20),
        ),
        migrations.AddField(
            model_name='word',
            name='part_of_speech',
            field=models.CharField(blank=True, choices=[('adjective', 'Adjective'), ('adverb', 'Adverb'), ('conjunction', 'Conjunction'), ('interjection', 'Interjection'), ('noun', 'Noun'), ('number', 'Number'), ('preposition', 'Preposition'), ('pronoun', 'Pronoun'), ('verb', 'Verb')], default='', max_length=20),
        ),
        migrations.AddIndex(
            model_name='word',
            index=models.Index(fields=['part_of_speech'], name='words_word_part_of_67faeb_idx'),
        ),
        migrations.AddIndex(
            model_name='word',
            index=models.Index(fields=['article'], name='words_word_article_5cf77d_idx'),
        ),
        migrations.RunPython(infer_existing_metadata, migrations.RunPython.noop),
    ]
