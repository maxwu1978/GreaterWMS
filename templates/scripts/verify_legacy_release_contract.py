#!/usr/bin/env python3
"""Prevent the known legacy branch-integration regressions from returning."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(ROOT / 'scripts/verify_legacy_table_contract.py')], check=True)
dashboard = (ROOT / 'src/pages/dashboard/dashboard.vue').read_text()
assert '<operations-board' in dashboard, 'Warehouse operations board is missing'
assert 'mail-task-board' not in dashboard and 'MailTaskBoard' not in dashboard, 'Old dashboard mail panel returned'
assert not (ROOT / 'src/pages/dashboard/mailTaskBoard.vue').exists(), 'Remove the superseded dashboard mail panel'
config = json.loads((ROOT / 'vercel.json').read_text())
redirects = {entry['source']: entry['destination'] for entry in config.get('redirects', [])}
for entry in ('/mail2task', '/source-intake'):
    assert redirects.get(entry) == '/#/mail2task', f'Missing canonical redirect for {entry}'
layout = (ROOT / 'src/layouts/MainLayout.vue').read_text()
assert 'width: $q.screen.width' not in layout, 'Layout must use available content width'
assert not (ROOT.parent / 'frontend/package.json').exists(), 'React migration tree must remain separate'
print('Legacy release contract passed: canonical Mail2Task, original dashboard and responsive shell.')
