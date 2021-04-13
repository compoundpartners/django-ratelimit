from django.conf import settings
from django.utils.module_loading import import_string
from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin

from django_ratelimit import ALL, UNSAFE
from django_ratelimit.exceptions import Ratelimited
from django_ratelimit.core import is_ratelimited

RATELIMIT_PAGE = getattr(
    settings,
    'RATELIMIT_PAGE',
    '50/s',
)
RATELIMIT_MODULE = getattr(
    settings,
    'RATELIMIT_MODULE',
    '5/s',
)
STAGE = getattr(
    settings,
    'STAGE',
    'stage',
)
RATELIMIT_VIEW = getattr(
    settings,
    'RATELIMIT_VIEW',
    False,
)
RATELIMIT_SENTRY_ONLY = getattr(
    settings,
    'RATELIMIT_SENTRY_ONLY',
    False,
)
try:
    from sentry_sdk import capture_exception
    RATELIMIT_SENTRY = True
except ImportError:
    RATELIMIT_SENTRY = False


class RatelimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, Ratelimited):
            if RATELIMIT_SENTRY:
                capture_exception(exception)
            if RATELIMIT_SENTRY_ONLY:
                return None
            if RATELIMIT_VIEW:
                view = import_string(RATELIMIT_VIEW)
                return view(request, exception)
        return None


class RatelimitForAllViewsMiddleware(MiddlewareMixin):
    def get_rate(self, request):
        try:
            match = resolve(request.path_info)
        except:
            return None
        if match.url_name in ('pages-root', 'pages-details-by-slug'):
            return 'cms.page', RATELIMIT_PAGE
        elif hasattr(match, 'app_names') and not 'admin' in match.app_names:
            return str(match.func), RATELIMIT_MODULE
        return None

    def process_request(self, request):
        rate = self.get_rate(request)
        if rate:
            old_limited = getattr(request, 'limited', False)
            ratelimited = is_ratelimited(request=request,
                                         group=rate[0],
                                         key='ip' if STAGE == 'local' else 'header:x-forwarded-for',
                                         rate=rate[1],
                                         increment=True)
            request.limited = ratelimited or old_limited
            if ratelimited:
                if RATELIMIT_SENTRY:
                    capture_exception(Ratelimited())
                if RATELIMIT_SENTRY_ONLY:
                    return None
                # if RATELIMIT_VIEW:
                    # view = import_string(RATELIMIT_VIEW)
                    # return view(request, exception)
                raise Ratelimited()

