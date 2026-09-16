#!/usr/bin/env python3
"""Run legacy integration regressions with an isolated database and no network."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key in ('DATABASE_URL', 'RENDER', 'RENDER_SERVICE_ID', 'RENDER_EXTERNAL_URL'):
    os.environ.pop(key, None)
os.environ['DJANGO_SETTINGS_MODULE'] = 'greaterwms.settings'
os.environ['DEBUG'] = 'false'
os.environ['SECRET_KEY'] = 'local-regression-only-not-a-deployment-secret'


def deny_network(*args, **kwargs):
    raise RuntimeError('Network is disabled in the isolated regression runner')


socket.socket.connect = deny_network
socket.create_connection = deny_network

from django.conf import settings

settings.DATABASES = {
    'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:',
                'TEST': {'NAME': ':memory:'}}
}
settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.LOGGING = {'version': 1, 'disable_existing_loggers': False,
                    'handlers': {'null': {'class': 'logging.NullHandler'}},
                    'root': {'handlers': ['null']}}
settings.STATICFILES_DIRS = []

DEFAULT_LABELS = [
    'greaterwms.test_authorization',
    'asn.tests',
    'receiving.tests',
    'dn.tests',
    'asnserial.tests',
    'transport.tests',
    'dashboard.tests',
]

if __name__ == '__main__':
    import django
    from django.test.runner import DiscoverRunner

    labels = sys.argv[1:] or DEFAULT_LABELS
    with tempfile.TemporaryDirectory(prefix='greaterwms-regression-') as media:
        settings.MEDIA_ROOT = media
        django.setup()
        print(json.dumps({
            'head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
            'python': sys.version.split()[0], 'django': django.get_version(),
            'database': 'isolated in-memory SQLite', 'network': 'disabled', 'labels': labels,
        }), flush=True)
        sys.exit(bool(DiscoverRunner(verbosity=2, interactive=False).run_tests(labels)))
