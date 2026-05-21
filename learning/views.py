from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from Vocab_Buddy.streaks import get_user_streak_days
from grammar.models import GrammarPracticeSession
from words.models import UserWord, Word
from .forms import ReviewForm, QuizAnswerForm
from .models import QuizResult, ReviewSession
from .scheduler import SpacedRepetitionScheduler
import random


def index(request):
    return render(request, 'learning/index.html')


def home(request):
    """Render the dashboard-style home page using user's vocabulary stats."""
    context = {}
    if request.user.is_authenticated:
        uwords = list(UserWord.objects.filter(user=request.user).select_related('word'))
        total_words = len(uwords)
        mastered_words = 0
        review_due = 0
        grammar_practiced = GrammarPracticeSession.objects.filter(user=request.user).values('topic').distinct().count()
        streak_days = get_user_streak_days(request.user)
        for uw in uwords:
            try:
                acc = uw.get_accuracy()
            except Exception:
                acc = 0
            if acc and acc > 80:
                mastered_words += 1
            if not uw.last_reviewed:
                review_due += 1

        stats = [
            {'label': 'Total Words', 'value': total_words, 'color': 'bg-primary'},
            {'label': 'Words Mastered', 'value': mastered_words, 'color': 'bg-success'},
            {'label': 'Study Streak', 'value': f'🔥 {streak_days} day streak' if streak_days else '🔥 Start your streak', 'color': 'bg-accent'},
            {'label': 'Grammar Practiced', 'value': grammar_practiced, 'color': 'bg-chart-4'},
        ]
        compact_stats = [
            {'label': 'Words', 'value': total_words},
            {'label': 'Mastered', 'value': mastered_words},
            {'label': 'Grammar', 'value': grammar_practiced},
            {'label': 'Due', 'value': review_due},
        ]
        today_plan = [
            {
                'label': 'Review flashcards',
                'detail': f'{review_due or total_words} ready',
                'done': total_words > 0 and review_due == 0,
                'href': reverse('learning:review_start'),
            },
            {
                'label': 'Practice grammar',
                'detail': 'One short topic',
                'done': grammar_practiced > 0,
                'href': reverse('grammar:topic_list'),
            },
            {
                'label': 'Add a new word',
                'detail': 'Grow your deck',
                'done': total_words > 0,
                'href': reverse('words:add_word'),
            },
        ]
        today = timezone.localdate()
        start_day = today - timedelta(days=6)
        counts_by_day = {start_day + timedelta(days=offset): 0 for offset in range(7)}

        for uw in uwords:
            added_day = timezone.localdate(uw.added_at)
            if start_day <= added_day <= today:
                counts_by_day[added_day] += 1

        weekly_data = []
        max_words = max(counts_by_day.values(), default=0)
        chart_max = max(1, max_words)
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

        for offset in range(7):
            current_day = start_day + timedelta(days=offset)
            count = counts_by_day[current_day]
            weekly_data.append({
                'day': day_names[current_day.weekday()],
                'date': current_day.strftime('%b %d'),
                'words': count,
                'height': max(8, round((count / chart_max) * 100)) if count else 8,
                'is_today': current_day == today,
            })

        weekly_total = sum(point['words'] for point in weekly_data)

        context.update({
            'stats': stats,
            'weekly_data': weekly_data,
            'weekly_total': weekly_total,
            'weekly_start_label': start_day.strftime('%b %d'),
            'weekly_end_label': today.strftime('%b %d'),
            'total_words': total_words,
            'mastered_words': mastered_words,
            'review_due': review_due,
            'grammar_practiced': grammar_practiced,
            'streak_days': streak_days,
            'compact_stats': compact_stats,
            'today_plan': today_plan,
        })

    return render(request, 'home.html', context)


def _parse_examples(raw_examples):
    lines = [line.strip() for line in (raw_examples or '').splitlines() if line.strip()]
    return lines[:2]


def _noun_examples(word):
    noun = word.noun_text()
    nominative_article = word.nominative_article()
    accusative_article = word.accusative_article()
    if not noun or not nominative_article:
        return []

    if word.gender == 'plural' or word.article == 'plural':
        return [
            {
                'before': '',
                'article': 'Die',
                'colored': noun,
                'after': ' sind neu.',
                'translation': f'The {word.translation} are new.',
            },
            {
                'before': 'Ich sehe ',
                'article': accusative_article,
                'colored': noun,
                'after': '.',
                'translation': f'I see the {word.translation}.',
            },
        ]

    return [
        {
            'before': '',
            'article': nominative_article[:1].upper() + nominative_article[1:],
            'colored': noun,
            'after': ' ist neu.',
            'translation': f'The {word.translation} is new.',
        },
        {
            'before': 'Ich sehe ',
            'article': accusative_article,
            'colored': noun,
            'after': '.',
            'translation': f'I see the {word.translation}.',
        },
    ]


def _parse_verb_forms(raw_text):
    meta = {
        'verb': '',
        'meaning': '',
        'type': '',
        'participle': '',
        'auxiliary': '',
    }
    present_rows = []
    past_rows = []
    section = None

    for line in [line.strip() for line in (raw_text or '').splitlines() if line.strip()]:
        if line.startswith('VERB:'):
            meta['verb'] = line.split(':', 1)[1].strip()
            continue
        if line.startswith('MEANING:'):
            meta['meaning'] = line.split(':', 1)[1].strip()
            continue
        if line.startswith('TYPE:'):
            meta['type'] = line.split(':', 1)[1].strip()
            continue
        if line.startswith('PRESENT TENSE:'):
            section = 'present'
            continue
        if line.startswith('PAST TENSE'):
            section = 'past'
            continue
        if line.startswith('PERFECT TENSE:'):
            section = 'perfect'
            continue
        if section == 'perfect':
            if line.startswith('Past Participle:'):
                meta['participle'] = line.split(':', 1)[1].strip()
            elif line.startswith('Auxiliary:'):
                meta['auxiliary'] = line.split(':', 1)[1].strip()
            continue
        if section in {'present', 'past'}:
            parts = line.split(None, 1)
            if len(parts) == 2:
                row = {'pronoun': parts[0].strip(), 'form': parts[1].strip()}
                if section == 'present':
                    present_rows.append(row)
                else:
                    past_rows.append(row)

    return {
        'meta': meta,
        'present_rows': present_rows,
        'past_rows': past_rows,
    }


def _grammar_hint_for_word(word, is_verb, verb_forms_data):
    text = (word.word or '').strip()
    lower_text = text.lower()

    if word.part_of_speech == 'noun':
        display_word = word.display_word()
        sentence_display_word = display_word[:1].upper() + display_word[1:] if display_word else display_word
        article_label = word.nominative_article() if word.nominative_article() in {'der', 'die', 'das'} else 'the article'
        gender_label = word.gender or 'noun gender'
        return {
            'title': 'Grammar Focus: Article and Gender',
            'topic_slug': 'definite-articles',
            'topic_label': 'Practice Articles',
            'bullets': [
                f'{sentence_display_word} is a noun.',
                f'Learn it with {article_label}; this marks {gender_label}.',
                'The article can change when the noun is used in a different case.',
            ],
            'pattern': 'article + noun',
            'example': f'{sentence_display_word} ist neu. - The {word.translation} is new.',
        }

    if is_verb:
        meta = (verb_forms_data or {}).get('meta', {})
        verb_type = (meta.get('type') or '').lower()
        verb = meta.get('verb') or text

        if 'modal' in verb_type or lower_text in {'koennen', 'können', 'muessen', 'müssen', 'wollen', 'sollen', 'duerfen', 'dürfen', 'moegen', 'mögen'}:
            return {
                'title': 'Grammar Focus: Modal Verb',
                'topic_slug': 'modal-verbs',
                'topic_label': 'Practice Modal Verbs',
                'bullets': [
                    f'{verb} is a modal verb.',
                    'The conjugated modal verb stays in position 2.',
                    'The main action verb goes to the end in infinitive form.',
                ],
                'pattern': 'Subject + modal verb + details + infinitive',
                'example': 'Ich darf heute Deutsch lernen. - I am allowed to learn German today.' if lower_text in {'duerfen', 'dürfen'} else 'Ich kann heute Deutsch lernen. - I can learn German today.',
            }

        if 'separable' in verb_type:
            return {
                'title': 'Grammar Focus: Separable Verb',
                'topic_slug': 'separable-verbs',
                'topic_label': 'Practice Separable Verbs',
                'bullets': [
                    f'{verb} is used like a separable verb.',
                    'The conjugated stem goes in position 2.',
                    'The prefix moves to the end of the main clause.',
                ],
                'pattern': 'Subject + verb stem + details + prefix',
                'example': 'Ich stehe um sieben Uhr auf. - I get up at seven.',
            }

        return {
            'title': 'Grammar Focus: Verb Position',
            'topic_slug': 'verb-position-main-clauses',
            'topic_label': 'Practice Verb Position',
            'bullets': [
                f'{verb} is a verb, so word order matters.',
                'In a main clause, the conjugated verb is usually in position 2.',
                'A time phrase can come first, but the verb still stays second.',
            ],
            'pattern': 'First idea + conjugated verb + subject + details',
            'example': 'Heute lerne ich Deutsch. - Today I am learning German.',
        }

    if lower_text.startswith(('der ', 'die ', 'das ')):
        return {
            'title': 'Grammar Focus: Article and Gender',
            'topic_slug': 'definite-articles',
            'topic_label': 'Practice Articles',
            'bullets': [
                'German nouns should be learned with their article.',
                'The article shows grammatical gender: der, die, or das.',
                'The article can change when the noun is used in a different case.',
            ],
            'pattern': 'article + noun',
            'example': 'Das Buch ist neu. - The book is new.',
        }

    return {
        'title': 'Grammar Focus: Cases',
        'topic_slug': 'nominative-accusative',
        'topic_label': 'Practice Cases',
        'bullets': [
            'Think about the role this word plays in the sentence.',
            'Subjects use nominative case.',
            'Direct objects usually use accusative case.',
        ],
        'pattern': 'subject + verb + direct object',
        'example': 'Der Mann sieht den Hund. - The man sees the dog.',
    }


@login_required
def review_start(request):
    """Start review session with per-word learning content."""
    selected_level = request.GET.get('level', '').strip().upper()
    valid_levels = [level for level, _label in Word.CEFR_LEVELS]
    if selected_level not in valid_levels:
        selected_level = ''

    selected_pos = request.GET.get('pos', '').strip().lower()
    valid_pos = [value for value, _label in Word.PARTS_OF_SPEECH]
    if selected_pos not in valid_pos:
        selected_pos = ''

    selected_article = request.GET.get('article', '').strip().lower()
    if selected_article not in {'der', 'die', 'das', 'plural'}:
        selected_article = ''

    base_qs = UserWord.objects.filter(user=request.user).select_related('word')
    counts_by_level = {
        level: base_qs.filter(word__cefr_level=level).count()
        for level in valid_levels
    }
    total_words = base_qs.count()
    cefr_with_counts = [
        (level, label, counts_by_level.get(level, 0))
        for level, label in Word.CEFR_LEVELS
    ]
    pos_with_counts = [
        (value, label, base_qs.filter(word__part_of_speech=value).count())
        for value, label in Word.PARTS_OF_SPEECH
    ]
    article_with_counts = [
        ('der', 'der', base_qs.filter(word__article='der').count()),
        ('das', 'das', base_qs.filter(word__article='das').count()),
        ('die', 'die', base_qs.filter(word__article='die', word__gender='feminine').count()),
        ('plural', 'plural die', base_qs.filter(word__gender='plural').count()),
    ]

    uwords_qs = base_qs
    if selected_level:
        uwords_qs = uwords_qs.filter(word__cefr_level=selected_level)
    if selected_pos:
        uwords_qs = uwords_qs.filter(word__part_of_speech=selected_pos)
    if selected_article:
        if selected_article == 'plural':
            uwords_qs = uwords_qs.filter(word__gender='plural')
        else:
            uwords_qs = uwords_qs.filter(word__article=selected_article)

    if not uwords_qs.exists():
        return render(request, 'learning/review_done.html', {
            'selected_level': selected_level,
            'selected_pos': selected_pos,
            'selected_article': selected_article,
            'cefr_with_counts': cefr_with_counts,
            'pos_with_counts': pos_with_counts,
            'article_with_counts': article_with_counts,
            'total_words': total_words,
        })

    level_map = {'A1': 0, 'A2': 1, 'B1': 2, 'B2': 3, 'C1': 4, 'C2': 5}
    cards = []

    for uw in uwords_qs:
        review_count = uw.review_count or 0
        correct_count = uw.correct_count or 0
        incorrect = max(0, review_count - correct_count)
        level_weight = level_map.get(uw.word.cefr_level, 0)
        weight = 1 + incorrect * 3 + level_weight

        examples = _parse_examples(uw.word.example_sentences or '')
        example_structures = _noun_examples(uw.word) if uw.word.part_of_speech == 'noun' else []
        verb_forms_raw = uw.word.verb_forms or ''
        is_verb = uw.word.is_verb or bool(verb_forms_raw)
        verb_forms_data = _parse_verb_forms(verb_forms_raw) if is_verb and verb_forms_raw else None
        grammar_hint = _grammar_hint_for_word(uw.word, is_verb, verb_forms_data)

        cards.append({
            'pk': uw.pk,
            'front': uw.word.display_word(),
            'back': uw.word.translation,
            'level': uw.word.cefr_level,
            'part_of_speech': uw.word.part_of_speech,
            'part_of_speech_label': uw.word.get_part_of_speech_display() if uw.word.part_of_speech else '',
            'article': uw.word.article,
            'gender': uw.word.gender,
            'noun_text': uw.word.noun_text(),
            'nominative_article': uw.word.nominative_article(),
            'accusative_article': uw.word.accusative_article(),
            'category': uw.word.category,
            'article_color_key': uw.word.article_color_key(),
            'weight': weight,
            'examples': examples,
            'example_structures': example_structures,
            'is_verb': is_verb,
            'verb_forms_data': verb_forms_data,
            'grammar_hint': grammar_hint,
        })

    import json
    cards_json_str = json.dumps(cards, ensure_ascii=False)

    context = {
        'uwords': uwords_qs,
        'cards_json_str': cards_json_str,
        'cards': cards,
        'selected_level': selected_level,
        'selected_pos': selected_pos,
        'selected_article': selected_article,
        'cefr_with_counts': cefr_with_counts,
        'pos_with_counts': pos_with_counts,
        'article_with_counts': article_with_counts,
        'total_words': total_words,
    }
    return render(request, 'learning/review_session.html', context)


@login_required
def review_next(request):
    """Complete review session: mark all words as reviewed"""
    if request.method == 'POST':
        # Accept reviewed pks from the client (comma-separated) and mark them reviewed
        pks_csv = request.POST.get('reviewed_pks', '')
        pks = [int(x) for x in pks_csv.split(',') if x.strip().isdigit()]
        for pk in pks:
            try:
                uword = UserWord.objects.get(pk=pk, user=request.user)
                uword.review_count = (uword.review_count or 0) + 1
                uword.correct_count = (uword.correct_count or 0) + 1
                uword.last_reviewed = timezone.now()
                uword.save()
            except UserWord.DoesNotExist:
                pass
        return render(request, 'learning/review_done.html')
    
    return redirect('learning:review_start')


@login_required
def quiz_start(request):
    """Start quiz: select 5 words and generate multiple-choice questions"""
    # Get up to 5 random words from user's vocabulary
    user_words = list(UserWord.objects.filter(user=request.user).values_list('word__word', 'word__translation', 'pk'))
    if len(user_words) < 4:
        return render(request, 'learning/quiz_insufficient.html', {'needed': 4, 'have': len(user_words)})
    
    quiz_words = random.sample(user_words, min(5, len(user_words)))
    questions = []
    
    # Generate multiple-choice questions
    for word_text, translation, word_pk in quiz_words:
        # Get 3 wrong answers from other words
        other_translations = [w[1] for w in user_words if w[0] != word_text]
        wrong_answers = random.sample(other_translations, min(3, len(other_translations)))
        
        # Create options list
        options = [translation] + wrong_answers[:3]
        random.shuffle(options)
        correct_idx = options.index(translation)
        
        questions.append({
            'word': word_text,
            'translation': translation,
            'options': options,
            'correct': correct_idx
        })
    
    request.session['quiz_questions'] = questions
    request.session['quiz_answers'] = []
    request.session['quiz_score'] = 0
    return redirect('learning:quiz_question', qid=0)


@login_required
def quiz_question(request, qid):
    """Show quiz question with multiple-choice options"""
    questions = request.session.get('quiz_questions', [])
    if qid >= len(questions):
        return redirect('learning:quiz_results')

    question = questions[qid]
    
    if request.method == 'POST':
        selected_idx = int(request.POST.get('answer', -1))
        is_correct = selected_idx == question['correct']
        
        quiz_answers = request.session.get('quiz_answers', [])
        quiz_answers.append({
            'question': question['word'],
            'correct_answer': question['translation'],
            'user_answer': question['options'][selected_idx] if 0 <= selected_idx < len(question['options']) else 'Invalid',
            'is_correct': is_correct
        })
        request.session['quiz_answers'] = quiz_answers
        
        if is_correct:
            request.session['quiz_score'] = request.session.get('quiz_score', 0) + 1
        
        return redirect('learning:quiz_question', qid=qid+1)
    
    # Display multiple-choice question
    progress_percent = int((qid / len(questions)) * 100) if len(questions) > 0 else 0
    option_letters = ['A', 'B', 'C', 'D']
    options_with_labels = list(zip(option_letters, question['options']))
    context = {
        'question_num': qid + 1,
        'total_questions': len(questions),
        'word': question['word'],
        'options': question['options'],
        'options_with_labels': options_with_labels,

        'qid': qid,
        'progress_percent': progress_percent,
    }
    return render(request, 'learning/quiz_question.html', context)


@login_required
def quiz_results(request):
    """Display quiz results"""
    answers = request.session.get('quiz_answers', [])
    total = len(answers)
    correct = sum(1 for a in answers if a.get('is_correct'))

    if request.user.is_authenticated and total > 0:
        QuizResult.objects.create(user=request.user, total=total, correct=correct)
        for ans in answers:
            try:
                uw = UserWord.objects.get(user=request.user, word__word=ans.get('question'))
                uw.review_count = (uw.review_count or 0) + 1
                if ans.get('is_correct'):
                    uw.correct_count = (uw.correct_count or 0) + 1
                uw.last_reviewed = timezone.now()
                uw.save()
            except UserWord.DoesNotExist:
                continue

    return render(request, 'learning/quiz_results.html', {'answers': answers, 'total': total, 'correct': correct})


@login_required
def verb_info(request, verb):
    """Display verb conjugation info from AI"""
    svc = GroqAIService()
    info = svc.get_verb_info(verb)
    return render(request, 'learning/verb_info.html', {'verb': verb, 'info': info})
