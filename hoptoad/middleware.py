import logging
import re

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import Http404

from hoptoad import get_hoptoad_settings
from hoptoad.api import htv2

logger = logging.getLogger(__name__)


class HoptoadNotifierMiddleware(object):

    def __init__(self):
        """Initialize the middleware."""
        hoptoad_settings = get_hoptoad_settings()
        self._init_middleware(hoptoad_settings)

    def _init_middleware(self, hoptoad_settings):
        if 'HOPTOAD_API_KEY' not in hoptoad_settings:
            raise MiddlewareNotUsed

        blacklisted_envs = hoptoad_settings.get("HOPTOAD_IGNORE_ENV", [])
        env_name = hoptoad_settings.get("HOPTOAD_ENV_NAME", None)

        if env_name in blacklisted_envs:
            raise MiddlewareNotUsed

        if settings.DEBUG:
            if not hoptoad_settings.get('HOPTOAD_NOTIFY_WHILE_DEBUG', False):
                raise MiddlewareNotUsed

        self.timeout = hoptoad_settings.get('HOPTOAD_TIMEOUT', None)
        self.notify_404 = hoptoad_settings.get('HOPTOAD_NOTIFY_404', False)
        self.notify_403 = hoptoad_settings.get('HOPTOAD_NOTIFY_403', False)

        ignore_agents = hoptoad_settings.get('HOPTOAD_IGNORE_AGENTS', [])
        self.ignore_agents = map(re.compile, ignore_agents)

        #self.handler = get_handler()

    def _ignore(self, request):
        """Return True if the given request should be ignored,
        False otherwise.

        """
        ua = request.META.get('HTTP_USER_AGENT', '')
        return any(i.search(ua) for i in self.ignore_agents)

    def process_response(self, request, response):
        """Process a reponse object.

        Hoptoad will be notified of a 404 error if the response is a 404
        and 404 tracking is enabled in the settings.

        Hoptoad will be notified of a 403 error if the response is a 403
        and 403 tracking is enabled in the settings.

        Regardless of whether Hoptoad is notified, the reponse object will
        be returned unchanged.

        """
        if self._ignore(request):
            return response

        sc = response.status_code
        if sc in [404, 403] and getattr(self, "notify_%d" % sc):
            payload = htv2.generate_payload(request, sc, exception=None)
            #self.handler.enqueue(payload, self.timeout)
            htv2.report.delay(payload, self.timeout)

        return response

    def process_exception(self, request, exc):
        """Process an exception.

        Hoptoad will be notified of the exception and None will be
        returned so that Django's normal exception handling will then
        be used.

        """
        if self._ignore(request):
            return None

        if isinstance(exc, Http404) and not self.notify_404:
            return None

        payload = htv2.generate_payload(request, None, exception=exc)
        htv2.report.delay(payload, self.timeout)

        return None
