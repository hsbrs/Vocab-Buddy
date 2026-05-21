from django import forms
from django.core.exceptions import ValidationError
from .models import Word, UserWord
from ai_service import GroqAIService


class AddWordForm(forms.Form):
    """Form to add a new German word"""
    
    word = forms.CharField(
        label='German Word',
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter a German word or phrase',
            'autofocus': True,
        })
    )
    
    def clean_word(self):
        word_input = self.cleaned_data['word'].strip()

        def parse_word_response(ai_response):
            lines = [line.rstrip() for line in ai_response.splitlines()]
            word = ''
            translation = ''
            cefr_level = ''
            part_of_speech = ''
            article = ''
            gender = ''
            plural_form = ''
            category = ''
            examples = []
            verb_forms_lines = []
            section = None

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith('WORD:'):
                    word = line.split(':', 1)[1].strip()
                    section = None
                    continue
                if line.startswith('TRANSLATION:'):
                    translation = line.split(':', 1)[1].strip()
                    section = None
                    continue
                if line.startswith('CEFR:'):
                    cefr_level = line.split(':', 1)[1].strip()
                    section = None
                    continue
                if line.startswith('PART_OF_SPEECH:'):
                    part_of_speech = line.split(':', 1)[1].strip().lower()
                    section = None
                    continue
                if line.startswith('ARTICLE:'):
                    article = line.split(':', 1)[1].strip().lower()
                    section = None
                    continue
                if line.startswith('GENDER:'):
                    gender = line.split(':', 1)[1].strip().lower()
                    section = None
                    continue
                if line.startswith('PLURAL:'):
                    plural_form = line.split(':', 1)[1].strip()
                    section = None
                    continue
                if line.startswith('CATEGORY:'):
                    category = line.split(':', 1)[1].strip()
                    section = None
                    continue
                if line.startswith('EXAMPLES:'):
                    section = 'examples'
                    continue
                if line.startswith('VERB_FORMS:'):
                    section = 'verb_forms'
                    continue

                if section == 'examples':
                    examples.append(line.lstrip('0123456789. ').strip())
                elif section == 'verb_forms':
                    verb_forms_lines.append(raw_line.rstrip())

            valid_levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
            if not word or not translation or cefr_level not in valid_levels:
                raise ValueError('Invalid response format')

            verb_forms_text = '\n'.join([line for line in verb_forms_lines if line]).strip()
            parsed_verb_forms = '' if verb_forms_text.lower() == 'not a verb' else verb_forms_text
            valid_pos = [choice[0] for choice in Word.PARTS_OF_SPEECH]
            valid_articles = ['', 'der', 'die', 'das', 'plural']
            valid_genders = ['', 'masculine', 'feminine', 'neuter', 'plural']

            if part_of_speech not in valid_pos:
                if parsed_verb_forms:
                    part_of_speech = 'verb'
                elif word.lower().startswith(('der ', 'die ', 'das ')):
                    part_of_speech = 'noun'
                else:
                    part_of_speech = ''

            if article in {'none', 'no article', 'n/a'}:
                article = ''
            if gender in {'none', 'n/a'}:
                gender = ''
            if plural_form.lower() in {'none', 'n/a', 'not a noun'}:
                plural_form = ''
            if article not in valid_articles:
                article = ''
            if gender not in valid_genders:
                gender = ''

            if part_of_speech == 'noun' and not article:
                lower_word = word.lower()
                if lower_word.startswith(('der ', 'die ', 'das ')):
                    article = lower_word.split(' ', 1)[0]
                    gender = {'der': 'masculine', 'die': 'feminine', 'das': 'neuter'}.get(article, gender)
            if part_of_speech != 'noun':
                article = ''
                gender = ''
                plural_form = ''
            if part_of_speech == 'noun':
                for prefix in ('der ', 'die ', 'das '):
                    if word.lower().startswith(prefix):
                        word = word[len(prefix):].strip()
                        break
                if word:
                    word = word[:1].upper() + word[1:]
                if plural_form:
                    plural_form = plural_form[:1].upper() + plural_form[1:]

            return {
                'parsed_word': word,
                'parsed_translation': translation,
                'parsed_cefr_level': cefr_level,
                'parsed_part_of_speech': part_of_speech,
                'parsed_article': article,
                'parsed_gender': gender,
                'parsed_plural_form': plural_form,
                'parsed_category': category,
                'parsed_example_sentences': '\n'.join([line for line in examples if line][:2]),
                'parsed_verb_forms': parsed_verb_forms,
                'parsed_is_verb': bool(parsed_verb_forms) or part_of_speech == 'verb',
            }

        def parse_verb_response(ai_response):
            lines = [line.rstrip() for line in ai_response.splitlines()]
            verb_forms_lines = []
            section = None

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith('VERB:'):
                    section = 'verb_forms'
                elif line.startswith('MEANING:'):
                    section = 'verb_forms'
                elif line.startswith('TYPE:'):
                    section = 'verb_forms'
                elif line.startswith('PRESENT TENSE:'):
                    section = 'verb_forms'
                elif line.startswith('PAST TENSE'):
                    section = 'verb_forms'
                elif line.startswith('PERFECT TENSE:'):
                    section = 'verb_forms'

                if section == 'verb_forms':
                    verb_forms_lines.append(raw_line.rstrip())

            verb_forms_text = '\n'.join([line for line in verb_forms_lines if line]).strip()
            if not verb_forms_text or verb_forms_text.lower() == 'not a verb':
                return ''
            return verb_forms_text
        
        if not word_input:
            raise ValidationError('Please enter a German word.')
        
        # Check if word already exists
        if Word.objects.filter(word__iexact=word_input).exists():
            raise ValidationError('This word already exists in the database.')
        
        # Validate with Groq AI
        try:
            ai_service = GroqAIService()
            ai_response = ai_service.get_word_info(word_input)
            
            if ai_response.strip().lower() == 'not german':
                raise ValidationError(
                    f'"{word_input}" does not appear to be a German word. '
                    'Please enter a valid German word or phrase.'
                )
            try:
                parsed = parse_word_response(ai_response)
                self.cleaned_data.update(parsed)

                if not self.cleaned_data['parsed_is_verb']:
                    verb_info_response = ai_service.get_verb_info(word_input)
                    parsed_verb_forms = parse_verb_response(verb_info_response)
                    if parsed_verb_forms:
                        self.cleaned_data['parsed_verb_forms'] = parsed_verb_forms
                        self.cleaned_data['parsed_is_verb'] = True
                        self.cleaned_data['parsed_part_of_speech'] = 'verb'

            except (ValueError, AttributeError):
                raise ValidationError(
                    'Could not parse word information. Please try another word.'
                )
        except Exception as e:
            raise ValidationError(
                f'Error validating word: {str(e)} Please try again.'
            )
        
        return word_input
