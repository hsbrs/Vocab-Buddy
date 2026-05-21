from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ai_service import GroqAIService
from words.models import UserWord
from .models import (
    GrammarCoachEntry,
    GrammarExercise,
    GrammarExerciseAttempt,
    GrammarPracticeSession,
    GrammarTopic,
)


PERSONAL_PRACTICE = {
    'noun-accusative': {
        'title': 'Accusative Articles',
        'summary': 'Practice der/die/das changes with nouns from your deck.',
        'level': 'A1',
    },
    'verb-position': {
        'title': 'Verb Position',
        'summary': 'Build main-clause word order from verbs you saved.',
        'level': 'A1',
    },
    'adjective-endings': {
        'title': 'Adjective Endings',
        'summary': 'Notice endings on adjective forms from your vocabulary.',
        'level': 'B1',
    },
}


def _practice_key(slug):
    return f'grammar_practice_{slug}'


def _topic_progress(user):
    sessions = GrammarPracticeSession.objects.filter(user=user).select_related('topic')
    progress = {}
    for session in sessions:
        current = progress.get(session.topic_id)
        if current is None or session.accuracy() > current['accuracy']:
            progress[session.topic_id] = {
                'accuracy': session.accuracy(),
                'correct': session.correct,
                'total': session.total,
            }
    return progress


def _personal_practice_key(kind):
    return f'personal_grammar_{kind}'


def _shuffle_options(options):
    import random
    labels = list(dict.fromkeys(options))
    random.shuffle(labels)
    return [(letter, label) for letter, label in zip(['A', 'B', 'C', 'D'], labels)]


def _option_letter(options, correct_label):
    return next(letter for letter, label in options if label == correct_label)


def _option_label(options, selected_letter):
    return next((label for letter, label in options if letter == selected_letter), '')


def _present_form(raw_text, pronoun):
    in_present = False
    for line in [line.strip() for line in (raw_text or '').splitlines() if line.strip()]:
        if line.startswith('PRESENT TENSE:'):
            in_present = True
            continue
        if line.startswith(('PAST TENSE', 'PERFECT TENSE:')):
            in_present = False
            continue
        if in_present:
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0] == pronoun:
                return parts[1].strip()
    return ''


def _noun_practice_items(user):
    uwords = list(UserWord.objects.filter(
        user=user,
        word__part_of_speech='noun',
        word__article__in=['der', 'die', 'das'],
    ).select_related('word')[:20])
    items = []
    for user_word in uwords:
        word = user_word.word
        noun = word.noun_text()
        correct = word.accusative_article()
        prompt = f'Ich kaufe ___ {noun}.'
        if word.article == 'der':
            explanation = f'{word.display_word()} is masculine. As a direct object, der changes to den.'
        elif word.article == 'die':
            explanation = f'{word.display_word()} is feminine. In accusative, die stays die.'
        else:
            explanation = f'{word.display_word()} is neuter. In accusative, das stays das.'
        options = _shuffle_options(['der', 'den', 'die', 'das'])
        correct_option = _option_letter(options, correct)
        items.append({
            'word_id': word.id,
            'prompt': prompt,
            'options': options,
            'correct_option': correct_option,
            'correct_label': correct,
            'explanation': explanation,
            'word_label': word.display_word(),
        })
    return items


def _verb_practice_items(user):
    uwords = list(UserWord.objects.filter(
        user=user,
        word__part_of_speech='verb',
        word__verb_forms__gt='',
    ).select_related('word')[:20])
    items = []
    for user_word in uwords:
        word = user_word.word
        verb = word.word
        ich_form = _present_form(word.verb_forms, 'ich')
        du_form = _present_form(word.verb_forms, 'du')
        wir_form = _present_form(word.verb_forms, 'wir')
        if not ich_form:
            continue
        prompt = f'Heute ___ ich. ({verb})'
        options = _shuffle_options([
            ich_form,
            verb,
            du_form or f'{verb}st',
            wir_form or verb,
        ])
        correct_option = _option_letter(options, ich_form)
        items.append({
            'word_id': word.id,
            'prompt': prompt,
            'options': options,
            'correct_option': correct_option,
            'correct_label': ich_form,
            'explanation': f'With a time phrase first, the conjugated verb stays in position 2: Heute {ich_form} ich.',
            'word_label': verb,
        })
    return items


def _adjective_practice_items(user):
    uwords = list(UserWord.objects.filter(
        user=user,
        word__part_of_speech='adjective',
    ).select_related('word')[:20])
    items = []
    for user_word in uwords:
        word = user_word.word
        adjective = word.word
        stem = adjective[:-2] if adjective.endswith('en') else adjective.rstrip('er')
        correct = adjective if adjective.endswith('en') else f'{stem}en'
        prompt = f'Ich nehme den ___ Bus. ({stem or adjective})'
        options = _shuffle_options([
            stem or adjective,
            f'{stem}e',
            f'{stem}en',
            f'{stem}er',
        ])
        correct_option = next((letter for letter, label in options if label == correct), options[0][0])
        items.append({
            'word_id': word.id,
            'prompt': prompt,
            'options': options,
            'correct_option': correct_option,
            'correct_label': correct,
            'explanation': 'After den with a masculine accusative noun, the adjective usually takes -en.',
            'word_label': adjective,
        })
    return items


def _personal_practice_items(user, kind):
    if kind == 'noun-accusative':
        return _noun_practice_items(user)
    if kind == 'verb-position':
        return _verb_practice_items(user)
    if kind == 'adjective-endings':
        return _adjective_practice_items(user)
    return []


def _personal_practice_summary(user):
    counts = {
        'noun-accusative': UserWord.objects.filter(user=user, word__part_of_speech='noun', word__article__in=['der', 'die', 'das']).count(),
        'verb-position': UserWord.objects.filter(user=user, word__part_of_speech='verb', word__verb_forms__gt='').count(),
        'adjective-endings': UserWord.objects.filter(user=user, word__part_of_speech='adjective').count(),
    }
    return [
        {
            'kind': kind,
            'title': config['title'],
            'summary': config['summary'],
            'level': config['level'],
            'count': counts[kind],
            'href': reverse('grammar:personal_practice', args=[kind]),
        }
        for kind, config in PERSONAL_PRACTICE.items()
    ]


@login_required
def topic_list(request):
    topics = GrammarTopic.objects.prefetch_related('exercises')
    progress = _topic_progress(request.user)
    for topic in topics:
        item = progress.get(topic.id)
        if not item:
            topic.progress_label = 'Not started'
            topic.progress_class = 'bg-secondary text-muted-foreground'
        elif item['total'] and item['correct'] == item['total']:
            topic.progress_label = 'Mastered'
            topic.progress_class = 'bg-success text-white'
        else:
            topic.progress_label = f"Practiced {item['accuracy']}%"
            topic.progress_class = 'bg-accent text-white'

    levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    topics_by_level = [
        {
            'level': level,
            'topics': [topic for topic in topics if topic.cefr_level == level],
        }
        for level in levels
    ]
    return render(request, 'grammar/index.html', {
        'topics_by_level': topics_by_level,
        'personal_practice': _personal_practice_summary(request.user),
    })


@login_required
def topic_detail(request, slug):
    topic = get_object_or_404(GrammarTopic.objects.prefetch_related('exercises'), slug=slug)
    best_session = GrammarPracticeSession.objects.filter(user=request.user, topic=topic).first()
    return render(request, 'grammar/topic_detail.html', {
        'topic': topic,
        'best_session': best_session,
    })


@login_required
def coach(request):
    entry = None
    recent_entries = GrammarCoachEntry.objects.filter(user=request.user)[:5]

    if request.method == 'POST':
        sentence = request.POST.get('sentence', '').strip()
        if not sentence:
            messages.error(request, 'Write a German sentence first.')
            return redirect('grammar:coach')

        try:
            result = GroqAIService().check_grammar(sentence)
            entry = GrammarCoachEntry.objects.create(
                user=request.user,
                sentence=sentence,
                corrected_sentence=result.get('corrected', ''),
                is_correct=bool(result.get('is_correct', False)),
                cefr_level=result.get('cefr_level', ''),
                topic=result.get('topic', ''),
                explanation=result.get('explanation', ''),
                mistakes=result.get('mistakes') or [],
                examples=result.get('examples') or [],
            )
            recent_entries = GrammarCoachEntry.objects.filter(user=request.user)[:5]
        except Exception as exc:
            messages.error(request, f'Grammar coach could not analyze that sentence yet: {exc}')

    return render(request, 'grammar/coach.html', {
        'entry': entry,
        'recent_entries': recent_entries,
    })


@login_required
def personal_practice(request, kind):
    config = PERSONAL_PRACTICE.get(kind)
    if not config:
        return redirect('grammar:topic_list')

    items = _personal_practice_items(request.user, kind)
    if not items:
        return render(request, 'grammar/personal_empty.html', {
            'kind': kind,
            'practice': config,
        })

    request.session[_personal_practice_key(kind)] = {
        'items': items[:10],
        'answers': {},
    }
    request.session.modified = True
    return redirect('grammar:personal_question', kind=kind, position=0)


@login_required
def personal_question(request, kind, position):
    config = PERSONAL_PRACTICE.get(kind)
    if not config:
        return redirect('grammar:topic_list')

    practice = request.session.get(_personal_practice_key(kind))
    if not practice:
        return redirect('grammar:personal_practice', kind=kind)

    items = practice.get('items', [])
    if position >= len(items):
        return redirect('grammar:personal_results', kind=kind)

    item = items[position]
    answers = practice.get('answers', {})
    submitted_answer = answers.get(str(position))
    selected = submitted_answer.get('selected') if submitted_answer else ''

    if request.method == 'POST' and not submitted_answer:
        selected = request.POST.get('answer', '')
        submitted_answer = {
            'selected': selected,
            'selected_label': _option_label(item.get('options', []), selected),
            'is_correct': selected == item['correct_option'],
        }
        answers[str(position)] = submitted_answer
        practice['answers'] = answers
        request.session[_personal_practice_key(kind)] = practice
        request.session.modified = True

    return render(request, 'grammar/personal_question.html', {
        'kind': kind,
        'practice': config,
        'item': item,
        'position': position,
        'question_number': position + 1,
        'total': len(items),
        'progress_percent': round((position / len(items)) * 100) if items else 0,
        'submitted_answer': submitted_answer,
        'selected': selected,
        'next_position': position + 1,
    })


@login_required
def personal_results(request, kind):
    config = PERSONAL_PRACTICE.get(kind)
    if not config:
        return redirect('grammar:topic_list')

    practice = request.session.get(_personal_practice_key(kind))
    if not practice:
        return redirect('grammar:personal_practice', kind=kind)

    items = practice.get('items', [])
    answers = practice.get('answers', {})
    correct = sum(1 for answer in answers.values() if answer.get('is_correct'))
    total = len(items)
    rows = []
    for index, item in enumerate(items):
        answer = answers.get(str(index), {})
        rows.append({
            'item': item,
            'selected': answer.get('selected', ''),
            'selected_label': answer.get('selected_label', ''),
            'is_correct': answer.get('is_correct', False),
        })

    accuracy = round((correct / total) * 100) if total else 0
    return render(request, 'grammar/personal_results.html', {
        'kind': kind,
        'practice': config,
        'rows': rows,
        'correct': correct,
        'total': total,
        'accuracy': accuracy,
    })


@login_required
def exercise(request, slug):
    topic = get_object_or_404(GrammarTopic.objects.prefetch_related('exercises'), slug=slug)
    exercises = list(topic.exercises.all())
    if not exercises:
        return render(request, 'grammar/exercise_empty.html', {'topic': topic})

    request.session[_practice_key(slug)] = {
        'exercise_ids': [exercise.id for exercise in exercises],
        'answers': {},
        'saved_session_id': None,
    }
    request.session.modified = True
    return redirect('grammar:exercise_question', slug=slug, position=0)


@login_required
def exercise_question(request, slug, position):
    topic = get_object_or_404(GrammarTopic, slug=slug)
    practice = request.session.get(_practice_key(slug))
    if not practice:
        return redirect('grammar:exercise', slug=slug)

    exercise_ids = practice.get('exercise_ids', [])
    if position >= len(exercise_ids):
        return redirect('grammar:exercise_results', slug=slug)

    exercise = get_object_or_404(GrammarExercise, id=exercise_ids[position], topic=topic)
    answers = practice.get('answers', {})
    submitted_answer = answers.get(str(exercise.id))
    selected = submitted_answer.get('selected') if submitted_answer else ''

    if request.method == 'POST' and not submitted_answer:
        selected = request.POST.get('answer', '')
        answers[str(exercise.id)] = {
            'selected': selected,
            'is_correct': selected == exercise.correct_option,
        }
        practice['answers'] = answers
        request.session[_practice_key(slug)] = practice
        request.session.modified = True
        submitted_answer = answers[str(exercise.id)]

    return render(request, 'grammar/exercise_question.html', {
        'topic': topic,
        'exercise': exercise,
        'position': position,
        'question_number': position + 1,
        'total': len(exercise_ids),
        'progress_percent': round((position / len(exercise_ids)) * 100) if exercise_ids else 0,
        'submitted_answer': submitted_answer,
        'selected': selected,
        'next_position': position + 1,
    })


@login_required
def exercise_results(request, slug):
    topic = get_object_or_404(GrammarTopic, slug=slug)
    practice = request.session.get(_practice_key(slug))
    if not practice:
        return redirect('grammar:exercise', slug=slug)

    exercise_ids = practice.get('exercise_ids', [])
    answers = practice.get('answers', {})
    exercises = list(GrammarExercise.objects.filter(id__in=exercise_ids, topic=topic))
    exercises.sort(key=lambda exercise: exercise_ids.index(exercise.id))
    correct = sum(1 for answer in answers.values() if answer.get('is_correct'))
    total = len(exercises)

    saved_session_id = practice.get('saved_session_id')
    if saved_session_id:
        practice_session = GrammarPracticeSession.objects.get(id=saved_session_id, user=request.user)
    else:
        practice_session = GrammarPracticeSession.objects.create(
            user=request.user,
            topic=topic,
            correct=correct,
            total=total,
        )
        for exercise in exercises:
            answer = answers.get(str(exercise.id), {})
            GrammarExerciseAttempt.objects.create(
                session=practice_session,
                exercise=exercise,
                selected_option=answer.get('selected', ''),
                is_correct=answer.get('is_correct', False),
            )
        practice['saved_session_id'] = practice_session.id
        request.session[_practice_key(slug)] = practice
        request.session.modified = True

    rows = []
    for exercise in exercises:
        answer = answers.get(str(exercise.id), {})
        rows.append({
            'exercise': exercise,
            'selected': answer.get('selected', ''),
            'is_correct': answer.get('is_correct', False),
        })

    return render(request, 'grammar/exercise_results.html', {
        'topic': topic,
        'practice_session': practice_session,
        'rows': rows,
        'correct': correct,
        'total': total,
        'accuracy': practice_session.accuracy(),
    })
