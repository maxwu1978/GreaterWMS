#!/usr/bin/env node

/*
 * GreaterWMS outbound CLI test suite.
 *
 * Default mode is local and has no network or database side effects. Live mode
 * reads one disposable delivery note and requests server previews only. It
 * never confirms a write or changes outbound inventory.
 */

import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const CLI = resolve(ROOT, 'tools/greaterwms.mjs')

const CASES = Object.freeze([
  {
    id: 'L-001', phase: 'CLI access', title: 'Show outbound commands',
    args: ['--help'], expect: { exit: 0, text: 'Outbound: outbound create' },
    prompt: 'Use the listed outbound commands and keep every write behind dry-run and confirmation.'
  },
  {
    id: 'L-002', phase: 'CLI access', title: 'Check login status without exposing credentials',
    args: ['auth', 'status', '--json'], expect: { exit: 0, text: 'token_present' },
    prompt: 'If no session is available, log in for the selected environment without putting a password in the command line.'
  },
  {
    id: 'L-003', phase: 'Order creation', title: 'Reject delivery note without a customer',
    args: ['outbound', 'create', '--data', '{"creater":"warehouse"}', '--dry-run', '--json'],
    expect: { exit: 1, text: 'outbound create requires customer' },
    prompt: 'Provide the exact customer or owner from the customer order before creating the delivery note.'
  },
  {
    id: 'L-004', phase: 'Order creation', title: 'Reject delivery note without a creator',
    args: ['outbound', 'create', '--data', '{"customer":"TEST-CUSTOMER"}', '--dry-run', '--json'],
    expect: { exit: 1, text: 'outbound create requires creater' },
    prompt: 'Use the authenticated warehouse operator as creater; do not use an untracked personal label.'
  },
  {
    id: 'L-005', phase: 'Order creation', title: 'Require preview before delivery note creation',
    args: ['outbound', 'create', '--data', '{"customer":"TEST-CUSTOMER","creater":"warehouse"}'],
    expect: { exit: 1, text: 'outbound create is write-capable. Run --dry-run first' },
    prompt: 'Run the same payload with --dry-run --json, review the server preview, then confirm it.'
  },
  {
    id: 'L-006', phase: 'Order detail', title: 'Reject detail without a delivery note code',
    args: ['outbound-detail', 'create', '--data', '{"customer":"TEST-CUSTOMER","goods_code":["SKU-01"],"goods_qty":[1]}', '--dry-run', '--json'],
    expect: { exit: 1, text: 'outbound-detail create requires dn_code' },
    prompt: 'Use the delivery note code from the customer order; do not create a second outbound order.'
  },
  {
    id: 'L-007', phase: 'Order detail', title: 'Reject scalar SKU input',
    args: ['outbound-detail', 'create', '--data', '{"dn_code":"DN-TEST","customer":"TEST-CUSTOMER","goods_code":"SKU-01","goods_qty":[1]}', '--dry-run', '--json'],
    expect: { exit: 1, text: 'goods_code as a non-empty JSON array' },
    prompt: 'Use parallel goods_code and goods_qty arrays, one entry per SKU.'
  },
  {
    id: 'L-008', phase: 'Order detail', title: 'Reject scalar quantity input',
    args: ['outbound-detail', 'create', '--data', '{"dn_code":"DN-TEST","customer":"TEST-CUSTOMER","goods_code":["SKU-01"],"goods_qty":1}', '--dry-run', '--json'],
    expect: { exit: 1, text: 'goods_qty as a non-empty JSON array' },
    prompt: 'Use an integer quantity array matching the SKU array.'
  },
  {
    id: 'L-009', phase: 'Order detail', title: 'Reject mismatched SKU and quantity arrays',
    args: ['outbound-detail', 'create', '--data', '{"dn_code":"DN-TEST","customer":"TEST-CUSTOMER","goods_code":["SKU-01","SKU-02"],"goods_qty":[1]}', '--dry-run', '--json'],
    expect: { exit: 1, text: 'arrays with the same length' },
    prompt: 'Correct the line count before previewing; each SKU must have exactly one quantity.'
  },
  {
    id: 'L-010', phase: 'Order detail', title: 'Reject malformed JSON before any request',
    args: ['outbound-detail', 'create', '--data', '{bad-json', '--dry-run', '--json'],
    expect: { exit: 1, text: '--data must be a JSON object' },
    prompt: 'Correct the JSON. No outbound request was sent.'
  },
  {
    id: 'L-011', phase: 'Order detail', title: 'Normalize a missing data file error',
    args: ['outbound-detail', 'create', '--data-file', '/tmp/not-a-real-outbound.json', '--dry-run', '--json'],
    expect: { exit: 1, text: 'File not found' },
    prompt: 'Provide the real customer order file and preview it before creating the detail.'
  },
  {
    id: 'L-012', phase: 'Release', title: 'Require delivery note id for release',
    args: ['outbound', 'release', '--data', '{}', '--dry-run', '--json'],
    expect: { exit: 1, text: '--id is required' },
    prompt: 'List outbound orders and use the numeric delivery note id.'
  },
  {
    id: 'L-013', phase: 'Picking', title: 'Require id for picking work generation',
    args: ['outbound', 'order-release', '--data', '{}', '--dry-run', '--json'],
    expect: { exit: 1, text: '--id is required' },
    prompt: 'Use the delivery note id after release; order-release generates the picking work.'
  },
  {
    id: 'L-014', phase: 'Picking', title: 'Require id for pick confirmation',
    args: ['outbound', 'pick', '--data', '{}', '--dry-run', '--json'],
    expect: { exit: 1, text: '--id is required' },
    prompt: 'Read the picking list, then use the delivery note id and the scanned SKU/SN quantities.'
  },
  {
    id: 'L-015', phase: 'Dispatch', title: 'Require id for dispatch',
    args: ['outbound', 'dispatch', '--data', '{"driver":"Tom","staging_bin":"STAGE-LEFT-01"}', '--dry-run', '--json'],
    expect: { exit: 1, text: '--id is required' },
    prompt: 'Use a picked delivery note id and specify both the assigned driver and outbound staging slot.'
  },
  {
    id: 'L-016', phase: 'POD', title: 'Require id for proof of delivery',
    args: ['outbound', 'pod', '--data', '{"goodsData":[]}', '--dry-run', '--json'],
    expect: { exit: 1, text: '--id is required' },
    prompt: 'Use the in-transit delivery note id and submit one delivery line per shipped SKU.'
  },
  {
    id: 'L-017', phase: 'Cancellation', title: 'Require id for in-transit cancellation',
    args: ['outbound', 'cancel-intransit', '--data', '{"cancellation_note":"Test cancellation"}', '--dry-run', '--json'],
    expect: { exit: 1, text: '--id is required' },
    prompt: 'Only cancel a delivery note in status 5, and keep the cancellation reason in the audit trail.'
  },
  {
    id: 'L-018', phase: 'Confirmation safety', title: 'Require server token after confirm flag',
    args: ['outbound', 'release', '--id', '1', '--data', '{}', '--confirm', '--json'],
    expect: { exit: 1, text: 'outbound.release requires --confirmation-token' },
    prompt: 'Use the confirmation_token and evidence from a fresh server dry-run; do not reuse an old token.'
  },
  {
    id: 'L-019', phase: 'Confirmation safety', title: 'Require preview before dispatch confirmation',
    args: ['outbound', 'dispatch', '--id', '1', '--data', '{"driver":"Tom","staging_bin":"STAGE-LEFT-01"}'],
    expect: { exit: 1, text: 'outbound dispatch is write-capable. Run --dry-run first' },
    prompt: 'Preview dispatch first so the server can validate driver, staging capacity, and picked quantity.'
  },
  {
    id: 'L-020', phase: 'Confirmation safety', title: 'Require preview before POD confirmation',
    args: ['outbound', 'pod', '--id', '1', '--data', '{"goodsData":[]}', '--confirm', '--json'],
    expect: { exit: 1, text: 'outbound.pod requires --confirmation-token' },
    prompt: 'Run a POD dry-run and confirm only after all shipped SKU quantities and exception notes are reviewed.'
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

function liveCommandArgs (options) {
  if (options.url) return ['--url', options.url]
  return options.env ? ['--env', options.env] : []
}

function runLive (options) {
  const dnId = options['dn-id']
  const dnCode = options['dn-code']
  if (!dnId || !dnCode) throw new Error('Live mode requires --dn-id and --dn-code for a disposable test delivery note.')
  if (options.execute) throw new Error('Confirmed writes are not automated by this suite. Review previews, then use the normal CLI confirmation workflow on a disposable tenant.')

  const envArgs = liveCommandArgs(options)
  const sku = options.sku || 'TEST-SKU'
  const qty = Number(options.qty || 1)
  const driver = options.driver || 'Tom'
  const stagingBin = options['staging-bin'] || 'STAGE-LEFT-01'
  const podData = {
    dn_code: dnCode,
    goodsData: [{ goods_code: sku, intransit_qty: qty, delivery_damage_qty: 0 }]
  }
  const cases = [
    ['R-001', 'Read target delivery note', [...envArgs, 'outbound', 'get', '--id', dnId, '--json']],
    ['R-002', 'Read outbound details', [...envArgs, 'outbound-detail', 'list', '--query', JSON.stringify({ dn_code: dnCode }), '--json']],
    ['R-003', 'Read picking list', [...envArgs, 'outbound', 'picking-list', '--query', JSON.stringify({ dn_code: dnCode }), '--json']],
    ['R-004', 'Read dispatch records', [...envArgs, 'driver', 'dispatch-list', '--query', JSON.stringify({ dn_code: dnCode }), '--json']],
    ['R-005', 'Preview release', [...envArgs, 'outbound', 'release', '--id', dnId, '--data', JSON.stringify({ dn_code: dnCode }), '--dry-run', '--json']],
    ['R-006', 'Preview order-release', [...envArgs, 'outbound', 'order-release', '--id', dnId, '--data', JSON.stringify({ dn_code: dnCode }), '--dry-run', '--json']],
    ['R-007', 'Preview pick confirmation', [...envArgs, 'outbound', 'pick', '--id', dnId, '--data', JSON.stringify({ dn_code: dnCode }), '--dry-run', '--json']],
    ['R-008', 'Preview dispatch with driver and staging', [...envArgs, 'outbound', 'dispatch', '--id', dnId, '--data', JSON.stringify({ dn_code: dnCode, driver, staging_bin: stagingBin }), '--dry-run', '--json']],
    ['R-009', 'Preview POD quantity check', [...envArgs, 'outbound', 'pod', '--id', dnId, '--data', JSON.stringify(podData), '--dry-run', '--json']],
    ['R-010', 'Preview in-transit cancellation', [...envArgs, 'outbound', 'cancel-intransit', '--id', dnId, '--data', JSON.stringify({ dn_code: dnCode, cancellation_note: 'CLI suite preview only' }), '--dry-run', '--json']]
  ]

  return cases.map(([id, title, args]) => {
    const result = runCli(args, 60000)
    const output = outputOf(result).trim()
    const readOnly = Number(id.slice(3)) <= 4
    const pass = readOnly
      ? result.exit === 0
      : result.exit === 0 || (result.exit === 1 && output.includes('Next action:'))
    return {
      id,
      phase: readOnly ? 'Live read' : 'Live preview',
      title,
      pass,
      actual_exit: result.exit,
      output,
      prompt: readOnly
        ? 'Confirm the returned delivery note, details, picking list, and dispatch records belong to the disposable tenant.'
        : 'Review the server response. A blocked preview is acceptable when it gives a concrete Next action; do not confirm automatically.'
    }
  })
}

function printResults (results, json) {
  const summary = {
    total: results.length,
    passed: results.filter(item => item.pass).length,
    failed: results.filter(item => !item.pass).length,
    results
  }
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
