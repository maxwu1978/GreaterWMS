#!/usr/bin/env node

/*
 * GreaterWMS inbound CLI test suite.
 *
 * Default mode is local and has no network or database side effects. The live
 * mode only performs read commands and server previews unless --execute is
 * explicitly supplied. Confirmed writes are intentionally not automated here.
 */

import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const CLI = resolve(ROOT, 'tools/greaterwms.mjs')

const CASES = Object.freeze([
  {
    id: 'L-001', phase: 'CLI access', title: 'Show inbound commands',
    args: ['--help'], expect: { exit: 0, text: 'Inbound: asn eta|arrival|reserve-staging' },
    prompt: 'Use the listed command and keep writes behind dry-run and confirmation.'
  },
  {
    id: 'L-002', phase: 'CLI access', title: 'Check login status without exposing credentials',
    args: ['auth', 'status', '--json'], expect: { exit: 0, text: 'token_present' },
    prompt: 'If no session is available, run login for the selected environment; never put the password in a command line.'
  },
  {
    id: 'L-003', phase: 'Pre-arrival', title: 'Reject ASN creation with no trusted reference',
    args: ['asn', 'create', '--data', '{}', '--dry-run', '--json'], expect: { exit: 1, text: 'supplier or container_tracking' },
    prompt: 'Add a trusted supplier or container_tracking reference, then preview the ASN.'
  },
  {
    id: 'L-004', phase: 'Pre-arrival', title: 'Require dry-run before ASN creation',
    args: ['asn', 'create', '--data', '{"container_tracking":"TEST-CONTAINER"}'], expect: { exit: 1, text: 'Run --dry-run first' },
    prompt: 'Run the same command with --dry-run --json, review the server plan, then confirm it.'
  },
  {
    id: 'L-004A', phase: 'Pre-arrival', title: 'Require the server confirmation token',
    args: ['asn', 'eta', '--id', '1', '--data', '{}', '--confirm'], expect: { exit: 1, text: 'requires --confirmation-token' },
    prompt: 'Run a fresh dry-run, review the server preview, then reuse its confirmation_token and a stable idempotency key.'
  },
  {
    id: 'L-005', phase: 'Pre-arrival', title: 'Reject ASN detail without an existing ASN code',
    args: ['asn-detail', 'create', '--data', '{}', '--dry-run', '--json'], expect: { exit: 1, text: 'asn_code' },
    prompt: 'Find or create exactly one ASN for the load before adding SKU detail.'
  },
  {
    id: 'L-006', phase: 'Pre-arrival', title: 'Reject ETA update without ASN id',
    args: ['asn', 'eta', '--data', '{"expected_arrival_at":"2026-08-17T10:00:00-05:00"}', '--dry-run', '--json'], expect: { exit: 1, text: '--id is required' },
    prompt: 'Query the existing ASN by inbound order/container and use its numeric id.'
  },
  {
    id: 'L-007', phase: 'Pre-arrival', title: 'Reject staging reservation without ASN code',
    args: ['asn', 'reserve-staging', '--id', '1', '--data', '{"staging_bins":["STAGE-LEFT-01"]}', '--dry-run', '--json'], expect: { exit: 1, text: '--asn-code or asn_code' },
    prompt: 'Use the ASN code and reserve package/load-unit capacity, not raw SKU quantity.'
  },
  {
    id: 'L-008', phase: 'Pre-arrival', title: 'Reject malformed JSON before any request',
    args: ['asn', 'eta', '--id', '1', '--data', '{bad-json', '--dry-run', '--json'], expect: { exit: 1, text: '--data must be a JSON object' },
    prompt: 'Correct the JSON and rerun dry-run; no data was sent to the server.'
  },
  {
    id: 'L-009', phase: 'Pre-arrival', title: 'Reject missing Pack List file',
    args: ['packlist', 'import', '--asn-code', 'TEST-ASN', '--file', '/tmp/not-a-real-pack-list.xlsx', '--dry-run', '--json'], expect: { exit: 1, text: 'File not found' },
    prompt: 'Provide the actual workbook. Do not treat an inbound notice or Pick Ticket as a Pack List without checking its contents.'
  },
  {
    id: 'L-010', phase: 'Arrival', title: 'Require ASN id for physical arrival',
    args: ['asn', 'arrival', '--data', '{}', '--dry-run', '--json'], expect: { exit: 1, text: '--id is required' },
    prompt: 'Find the existing ASN first. Arrival is a physical event and must not create a new ASN.'
  },
  {
    id: 'L-011', phase: 'Unloading', title: 'Reject unloading without ASN code',
    args: ['asn', 'unload-start', '--id', '1', '--data', '{"unload_driver":"Tom","staging_bins":["STAGE-LEFT-01"]}', '--dry-run', '--json'], expect: { exit: 1, text: '--asn-code or asn_code' },
    prompt: 'Use the exact ASN code; the server will verify physical arrival, driver, and staging capacity.'
  },
  {
    id: 'L-012', phase: 'Receiving', title: 'Reject receiving putaway without ASN code',
    args: ['asn', 'putaway-bulk', '--data', '{"bin_name":"A1-01","res_data":[]}', '--dry-run', '--json'], expect: { exit: 1, text: '--asn-code or asn_code' },
    prompt: 'Use the ASN code and accepted quantity from receiving/QC; do not put away unresolved exceptions.'
  },
  {
    id: 'L-013', phase: 'QC', title: 'Reject inspection import without a workbook',
    args: ['inspection', 'import', '--asn-code', 'TEST-ASN', '--file', '/tmp/not-a-real-qc.xlsx', '--dry-run', '--json'], expect: { exit: 1, text: 'File not found' },
    prompt: 'Use the fixed QC workbook and preview it before importing; the workbook is evidence, not a Pack List.'
  },
  {
    id: 'L-014', phase: 'QC', title: 'Reject serial exception lookup without ASN code',
    args: ['serial', 'exceptions', '--json'], expect: { exit: 1, text: '--asn-code is required' },
    prompt: 'Use the ASN code to scope exception review to the current inbound load.'
  },
  {
    id: 'L-015', phase: 'Receiving', title: 'Reject receiving record without staging slots',
    args: ['receiving', 'create', '--data', '{"asn_code":"TEST-ASN"}', '--dry-run', '--json'], expect: { exit: 1, text: 'staging_bins' },
    prompt: 'Record the actual Stage-left/Stage-right locations where the unloaded goods are waiting.'
  },
  {
    id: 'L-016', phase: 'Receiving', title: 'Create a safe receiving dry-run plan',
    args: ['receiving', 'create', '--data', '{"asn_code":"TEST-ASN","staging_bins":["STAGE-LEFT-01"]}', '--dry-run', '--json'], expect: { exit: 0, text: 'dry_run' },
    prompt: 'Review SKU, quantity, stage, and operator scope before using the server confirmation token.'
  }
])

function parseArgs (values) {
  const options = {}
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index]
    if (!value.startsWith('--')) continue
    const key = value.slice(2)
    const next = values[index + 1]
    if (next && !next.startsWith('--')) {
      options[key] = next
      index += 1
    } else options[key] = true
  }
  return options
}

function runCli (args, timeout = 30000) {
  const result = spawnSync(process.execPath, [CLI, ...args], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout,
    env: { ...process.env }
  })
  return {
    exit: result.status === null ? 124 : result.status,
    stdout: result.stdout || '',
    stderr: result.stderr || ''
  }
}

function outputOf (result) {
  return `${result.stdout}\n${result.stderr}`
}

function runLocal () {
  return CASES.map((testCase) => {
    const result = runCli(testCase.args)
    const output = outputOf(result)
    return {
      ...testCase,
      pass: result.exit === testCase.expect.exit && output.includes(testCase.expect.text),
      actual_exit: result.exit,
      output: output.trim()
    }
  })
}

function runLive (options) {
  const asnId = options['asn-id']
  const asnCode = options['asn-code']
  if (!asnId || !asnCode) throw new Error('Live mode requires --asn-id and --asn-code for a disposable test ASN.')
  if (options.execute) throw new Error('Confirmed writes are not automated by this suite. Review each preview, then use the documented CLI confirmation workflow on a disposable tenant.')
  const envArgs = options.env ? ['--env', options.env] : []
  const driver = options.driver || 'Tom'
  const stagingBins = String(options['staging-bins'] || options['staging-bin'] || 'STAGE-LEFT-01')
    .split(',')
    .map(value => value.trim())
    .filter(Boolean)
  if (stagingBins.length === 0) throw new Error('Live mode requires at least one staging bin.')
  const sku = options.sku || 'TEST-SKU'
  const qty = Number(options.qty || 1)
  const cases = [
    ['R-001', 'Read target ASN', [...envArgs, 'asn', 'get', '--id', asnId, '--json']],
    ['R-002', 'List Pack List state', [...envArgs, 'packlist', 'list', '--asn-code', asnCode, '--json']],
    ['R-003', 'Preview ETA update', [...envArgs, 'asn', 'eta', '--id', asnId, '--data', '{"expected_arrival_at":"2099-01-01T10:00:00-05:00","source":"CLI_TEST_SUITE"}', '--dry-run', '--json']],
    ['R-004', 'Preview physical arrival', [...envArgs, 'asn', 'arrival', '--id', asnId, '--data', '{}', '--dry-run', '--json']],
    ['R-005', 'Preview staging reservation', [...envArgs, 'asn', 'reserve-staging', '--id', asnId, '--asn-code', asnCode, '--data', JSON.stringify({ asn_code: asnCode, staging_bins: stagingBins }), '--dry-run', '--json']],
    ['R-006', 'Preview unloading with driver and stage', [...envArgs, 'asn', 'unload-start', '--id', asnId, '--asn-code', asnCode, '--data', JSON.stringify({ asn_code: asnCode, unload_driver: driver, staging_bins: stagingBins }), '--dry-run', '--json']],
    ['R-007', 'Preview receiving quantity reconciliation', [...envArgs, 'asn', 'receive', '--id', asnId, '--asn-code', asnCode, '--data', JSON.stringify({ asn_code: asnCode, goodsData: [{ goods_code: sku, goods_actual_qty: qty }] }), '--dry-run', '--json']]
  ]
  if (options['detail-id']) {
    cases.push(['R-008', 'Preview final-bin putaway', [...envArgs, 'asn', 'putaway', '--id', options['detail-id'], '--data', JSON.stringify({ asn_code: asnCode, goods_code: sku, qty, bin_name: options['final-bin'] || 'A1-01', putaway_driver: driver }), '--dry-run', '--json']])
  }
  return cases.map(([id, title, args]) => {
    const result = runCli(args, 60000)
    const output = outputOf(result).trim()
    const readOnly = id === 'R-001' || id === 'R-002'
    const pass = readOnly
      ? result.exit === 0
      : result.exit === 0 || (result.exit === 1 && output.includes('Next action:'))
    return { id, phase: 'Live preview', title, pass, actual_exit: result.exit, output, prompt: 'Review this read/preview result; do not confirm automatically.' }
  })
}

function printResults (results, json) {
  const summary = { total: results.length, passed: results.filter(item => item.pass).length, failed: results.filter(item => !item.pass).length, results }
  if (json) {
    process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`)
    return summary
  }
  for (const result of results) {
    process.stdout.write(`${result.pass ? 'PASS' : 'FAIL'} ${result.id} ${result.title}\n`)
    if (!result.pass || result.prompt) process.stdout.write(`  Next action: ${result.prompt}\n`)
    if (!result.pass) process.stdout.write(`  Output: ${result.output.replace(/\n/g, ' | ')}\n`)
  }
  process.stdout.write(`\n${summary.passed}/${summary.total} cases passed\n`)
  return summary
}

function printCatalog (json) {
  const catalog = CASES.map(({ id, phase, title, prompt }) => ({ id, phase, title, prompt }))
  process.stdout.write(json ? `${JSON.stringify(catalog, null, 2)}\n` : `${catalog.map(item => `${item.id}\t${item.phase}\t${item.title}`).join('\n')}\n`)
}

function main () {
  const options = parseArgs(process.argv.slice(2))
  if (options.catalog) {
    printCatalog(Boolean(options.json))
    return
  }
  if (options.live) {
    printResults(runLive(options), Boolean(options.json))
    return
  }
  const summary = printResults(runLocal(), Boolean(options.json))
  if (summary.failed > 0) process.exitCode = 1
}

main()
