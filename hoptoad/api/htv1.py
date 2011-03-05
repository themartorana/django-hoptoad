import traceback
import urllib2
import yaml

from django.views.debug import get_safe_settings
from django.conf import settings

from hoptoad import get_hoptoad_settings


PROTECTED_PARAMS = frozenset(get_hoptoad_settings()
                             .get('HOPTOAD_PROTECTED_PARAMS', []))


def _parse_environment(request):
    """Return an environment mapping for a notification
    from the given request.

    """

    env = dict((str(k), str(v)) for (k, v) in get_safe_settings().items())
    env.update(dict((str(k), str(v)) for (k, v) in request.META.items()))

    env['REQUEST_URI'] = request.build_absolute_uri()

    return env


def _parse_traceback(trace):
    """Return the given traceback string formatted for a notification."""
    p_traceback = ["%s:%d:in '%s'" % (filename, lineno, funcname)
                   for filename, lineno, funcname, _
                   in traceback.extract_tb(trace)]

    p_traceback.reverse()
    return p_traceback


def _parse_message(exc):
    """Return a message for a notification from the given exception."""
    return '%s: %s' % (exc.__class__.__name__, unicode(exc))


def _parse_request(request):
    """Return a request mapping for a notification from the given request."""
    data = []
    for (k, v) in request.POST.items():
        try:
            data.append((str(k), str(v.encode('ascii', 'replace'))))
        except UnicodeEncodeError:
            data.append((str(k), repr(v)))
    if not data:
        for (k, v) in request.GET.items():
            try:
                data.append((str(k), str(v.encode('ascii', 'replace'))))
            except UnicodeEncodeError:
                data.append((str(k), repr(v)))
    data = dict(data)

    for k in PROTECTED_PARAMS.intersection(data.keys()):
        data[k] = '********************'

    return data


def _parse_session(session):
    """Return a request mapping for a notification from the given session."""
    try:
        session_keys = session.keys()
    except Exception:
        # It is possible, especially if you're using a 100% ACID-compliant
        # database, that an exception was thrown and the database has
        # stopped processing any further transactions without a rollback
        # issued.
        #
        # It shouldn't be the job of a middleware instance to issue a
        # rollback, so, we will just return an empty dictionary with the
        # error messages
        return {"SessionInfo": "Couldn't extract session because the database "
                               "had a failed transaction. "}
    else:
        if not session_keys:
            return {"SessionInfo": "No session information could be extracted"}

    try:
        session_items = session.items()
    except Exception:
        # Same reasoning as above for the session keys
        return {"SessionInfo": "Couldn't extract session because the database "
                               "had a failed transaction. "}
    else:
        return dict((str(k), str(v)) for (k, v) in session_items)


def _generate_payload(request,
                      exc=None,
                      trace=None,
                      message=None,
                      error_class=None):
    """Generate a YAML payload for a Hoptoad notification.

    Parameters:
    request -- A Django HTTPRequest.  This is required.

    Keyword parameters:
    exc -- A Python Exception object.  If this is not given the
           mess parameter must be.
    trace -- A Python Traceback object.  This is not required.
    message -- A string representing the error message.  If this is not
               given, the exc parameter must be.
    error_class -- A string representing the error class.  If this is not
                   given the excc parameter must be.
    """
    p_message = message if message else _parse_message(exc)
    p_error_class = error_class if error_class else exc.__class__.__name__
    p_traceback = _parse_traceback(trace) if trace else []
    p_environment = _parse_environment(request)
    p_request = _parse_request(request)
    p_session = _parse_session(request.session)

    return yaml.dump({'notice':
                      {'api_key': settings.HOPTOAD_API_KEY,
                       'error_class': p_error_class,
                       'error_message': p_message,
                       'backtrace':  p_traceback,
                       'request': {'url': request.build_absolute_uri(),
                                   'params': p_request},
                       'session': {'key': '', 'data': p_session},
                       'environment': p_environment,
    }}, default_flow_style=False)


def _ride_the_toad(payload, timeout):
    """Send a notification (an HTTP POST request) to Hoptoad.

    Parameters:
    payload -- the YAML payload for the request from _generate_payload()
    timeout -- the maximum timeout, in seconds, or None to use the default
    """
    headers = {'Content-Type': 'application/x-yaml',
               'Accept': 'text/xml, application/xml', }
    r = urllib2.Request('http://hoptoadapp.com/notices', payload, headers)
    try:
        if timeout:
            urllib2.urlopen(r, timeout=timeout)
        else:
            urllib2.urlopen(r)
    except urllib2.URLError:
        pass


def report(payload, timeout):
    return _ride_the_toad(payload, timeout)
