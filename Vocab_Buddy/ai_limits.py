from django.utils import timezone

from grammar.models import AIUsageEvent


GRAMMAR_COACH_DAILY_LIMIT = 10
WORD_ENRICHMENT_DAILY_LIMIT = 20
GLOBAL_AI_DAILY_LIMIT = 250


class AILimitReached(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


def _today_range():
    now = timezone.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _daily_count(**filters):
    start, now = _today_range()
    return AIUsageEvent.objects.filter(created_at__gte=start, created_at__lte=now, **filters).count()


def check_ai_limit(user, feature):
    feature_limits = {
        AIUsageEvent.FEATURE_GRAMMAR_COACH: GRAMMAR_COACH_DAILY_LIMIT,
        AIUsageEvent.FEATURE_WORD_ENRICHMENT: WORD_ENRICHMENT_DAILY_LIMIT,
    }
    feature_limit = feature_limits[feature]

    if _daily_count() >= GLOBAL_AI_DAILY_LIMIT:
        raise AILimitReached('Daily AI capacity has been reached. Please try again tomorrow.')

    if _daily_count(user=user, feature=feature) >= feature_limit:
        if feature == AIUsageEvent.FEATURE_GRAMMAR_COACH:
            raise AILimitReached(f'You have used today\'s {feature_limit} Grammar Coach checks. Please try again tomorrow.')
        raise AILimitReached(f'You have used today\'s {feature_limit} AI word additions. Please try again tomorrow.')


def record_ai_usage(user, feature):
    AIUsageEvent.objects.create(user=user, feature=feature)
