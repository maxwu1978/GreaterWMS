#!/usr/bin/env python3
"""Identify the checkout before a Cursor task; optionally require a clean work branch."""
import argparse
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--require-clean', action='store_true')
parser.add_argument('--require-work-branch', action='store_true')
args = parser.parse_args()


def git(*parts):
    return subprocess.check_output(['git', '-C', str(ROOT), *parts], text=True).strip()


remote = git('remote', 'get-url', 'origin')
if remote.startswith('git@github.com:'):
    repository = remote.split(':', 1)[1].removesuffix('.git')
else:
    parsed = urlsplit(remote)
    repository = parsed.path.strip('/').removesuffix('.git') if parsed.hostname == 'github.com' else ''
branch = git('branch', '--show-current')
dirty = bool(git('status', '--porcelain'))
errors = []
if repository.casefold() != 'maxwu1978/greaterwms':
    errors.append('origin is not maxwu1978/GreaterWMS')
if args.require_clean and dirty:
    errors.append('working tree has changes; inspect and preserve them')
if args.require_work_branch and (not branch or branch in ('main', 'master')):
    errors.append('create a work branch from the verified main before editing')
print(json.dumps({'root': str(ROOT), 'repository': repository, 'branch': branch or '(detached)',
                  'head': git('rev-parse', 'HEAD'), 'dirty': dirty, 'errors': errors}, indent=2))
raise SystemExit(bool(errors))
