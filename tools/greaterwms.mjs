#!/usr/bin/env node

import { readFileSync, statSync } from 'node:fs'
import { basename, resolve } from 'node:path'

const DEFAULT_URL = 'https://greaterwms-v2-test3-sn.onrender.com'

// Read aliases for the current GreaterWMS menu pages.
const READ_RESOURCES = Object.freeze({
  warehouse: '/warehouse/',
  bin: '/binset/',
  'bin-size': '/binsize/',
  'bin-property': '/binproperty/',
  sku: '/goods/',
  goods: '/goods/',
  'sku-unit': '/goodsunit/',
  'sku-class': '/goodsclass/',
  'sku-color': '/goodscolor/',
  'sku-brand': '/goodsbrand/',
  'sku-shape': '/goodsshape/',
  'sku-specs': '/goodsspecs/',
  'sku-origin': '/goodsorigin/',
  supplier: '/supplier/',
  customer: '/customer/',
  company: '/company/',
  staff: '/staff/',
  'staff-types': '/staff/type/',
  driver: '/driver/',
  stock: '/stock/list/',
  asn: '/asn/list/',
  'asn-detail': '/asn/detail/',
  outbound: '/dn/list/',
  'outbound-detail': '/dn/detail/',
  'staging-slots': '/staging/slots/',
  'staging-assignments': '/staging/assignments/',
  'dashboard-operations': '/dashboard/operations/',
  'dashboard-receipts': '/dashboard/receipts/',
  'dashboard-sales': '/dashboard/sales/'
})

const READ_ACTIONS = Object.freeze({
  'asn events': '/asn/events/',
  'outbound picking-list': '/dn/pickinglistfilter/',
  'driver dispatch-list': '/driver/dispatchlist/'
})

const LIST_ONLY_RESOURCES = new Set([
  'bin-property',
  'staff-types',
  'staging-slots',
  'staging-assignments',
  'dashboard-operations',
  'dashboard-receipts',
  'dashboard-sales'
])

// Creation and editing are enabled only for master-data pages in this phase.
const WRITE_RESOURCES = Object.freeze({
  warehouse: { path: '/warehouse/' },
  bin: { path: '/binset/' },
  'bin-size': { path: '/binsize/' },
  sku: { path: '/goods/' },
  goods: { path: '/goods/' },
  'sku-unit': { path: '/goodsunit/' },
  'sku-class': { path: '/goodsclass/' },
  'sku-color': { path: '/goodscolor/' },
  'sku-brand': { path: '/goodsbrand/' },
  'sku-shape': { path: '/goodsshape/' },
  'sku-specs': { path: '/goodsspecs/' },
  'sku-origin': { path: '/goodsorigin/' },
  supplier: { path: '/supplier/' },
  customer: { path: '/customer/' },
  company: { path: '/company/' },
  staff: { path: '/staff/' },
  driver: { path: '/driver/' }
})

// Destructive access is deliberately limited to one existing record at a time.
const DELETE_RESOURCES = Object.freeze({
  ...WRITE_RESOURCES,
  asn: { path: '/asn/list/' },
  outbound: { path: '/dn/list/' },
  'outbound-detail': { path: '/dn/detail/' }
})

function parseArgs (values) {
  const options = {}
  const positional = []
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index]
    if (!value.startsWith('--')) {
      positional.push(value)
      continue
    }
    const key = value.slice(2)
    const next = values[index + 1]
    if (!next || next.startsWith('--')) {
      options[key] = true
    } else {
      options[key] = next
      index += 1
    }
  }
  return { options, positional }
}

function baseUrl () {
  return (process.env.GREATERWMS_URL || DEFAULT_URL).replace(/\/$/, '')
}

function authHeaders () {
  const token = process.env.GREATERWMS_TOKEN
  if (!token) {
    throw new Error('GREATERWMS_TOKEN is required')
  }
  return {
    token,
    operator: process.env.GREATERWMS_OPERATOR || '',
    language: process.env.GREATERWMS_LANGUAGE || 'en-US'
  }
}

async function request (path, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) }
  let body = options.body
  if (options.json !== undefined) {
    headers['content-type'] = 'application/json'
    body = JSON.stringify(options.json)
  }
  const response = await fetch(`${baseUrl()}${path}`, {
    method: options.method || 'GET',
    headers,
    body
  })
  const text = await response.text()
  let payload
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    payload = { detail: text || response.statusText }
  }
  const applicationStatus = Number(payload && payload.status_code)
  const hasApplicationError = Number.isFinite(applicationStatus) && applicationStatus >= 400
  if (!response.ok || hasApplicationError) {
    const detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload)
    throw new Error(`HTTP ${response.ok ? applicationStatus : response.status}: ${detail}`)
  }
  return payload
}

function parseQuery (value) {
  if (value === undefined || value === null || value === '') return {}
  try {
    const parsed = JSON.parse(String(value))
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('must be a JSON object')
    }
    return parsed
  } catch (error) {
    throw new Error(`--query must be a JSON object: ${error.message}`)
  }
}

function queryPath (path, options) {
  const query = parseQuery(options.query)
  if (options.page !== undefined) query.page = options.page
  if (options['page-size'] !== undefined) query.page_size = options['page-size']
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const suffix = params.toString()
  return suffix ? `${path}?${suffix}` : path
}

function parseData (options) {
  const value = options['data-file']
    ? readFileSync(resolve(String(options['data-file'])), 'utf8')
    : options.data
  if (value === undefined || value === null || value === '') return {}
  try {
    const parsed = JSON.parse(String(value))
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('must be a JSON object')
    }
    return parsed
  } catch (error) {
    throw new Error(`--data must be a JSON object: ${error.message}`)
  }
}

function requireConfirmation (options, label) {
  if (!options['dry-run'] && !options.confirm) {
    throw new Error(`${label} is write-capable. Run --dry-run first, then repeat with --confirm.`)
  }
}

async function readResource (resource, action, options, json) {
  const path = READ_RESOURCES[resource]
  if (!path) return false
  if (action === 'list') {
    print(await request(queryPath(path, options)), json)
    return true
  }
  if (action === 'get') {
    if (LIST_ONLY_RESOURCES.has(resource)) {
      throw new Error(`Read-only resource '${resource}' supports list only.`)
    }
    if (!options.id) throw new Error('--id is required')
    print(await request(`${path}${encodeURIComponent(String(options.id))}/`), json)
    return true
  }
  if (['create', 'update', 'delete'].includes(action)) return false
  throw new Error(`Read-only resource '${resource}' supports list and get only.`)
}

async function readAction (command, options, json) {
  const path = READ_ACTIONS[command]
  if (!path) return false
  print(await request(queryPath(path, options)), json)
  return true
}

async function writeResource (resource, action, options, json) {
  const definition = WRITE_RESOURCES[resource]
  if (!definition) return false
  if (action === 'delete') return false
  if (!['create', 'update'].includes(action)) {
    throw new Error(`'${resource} ${action}' is not enabled yet. Delete remains disabled in this phase.`)
  }
  requireConfirmation(options, `${resource} ${action}`)
  const data = parseData(options)
  const id = options.id ? encodeURIComponent(String(options.id)) : ''
  if (action === 'update' && !id) throw new Error('--id is required for update')
  const endpoint = action === 'create' ? definition.path : `${definition.path}${id}/`
  const method = action === 'create' ? 'POST' : 'PATCH'
  if (options['dry-run']) {
    print({ dry_run: true, method, endpoint, resource, action, data }, json)
    return true
  }
  print(await request(endpoint, { method, json: data }), json)
  return true
}

async function deleteResource (resource, action, options, json) {
  const definition = DELETE_RESOURCES[resource]
  if (!definition || action !== 'delete') return false
  if (!options.id) throw new Error('--id is required for delete')
  if (!options['dry-run'] && !options.confirm) {
    throw new Error(`${resource} delete is destructive. Run --dry-run first, then repeat with --confirm.`)
  }
  const endpoint = `${definition.path}${encodeURIComponent(String(options.id))}/`
  if (options['dry-run']) {
    print({
      dry_run: true,
      destructive: true,
      method: 'DELETE',
      endpoint,
      resource,
      action,
      id: String(options.id),
      note: 'Single-record deletion only; Pack List and bulk cleanup are not supported.'
    }, json)
    return true
  }
  print(await request(endpoint, { method: 'DELETE' }), json)
  return true
}

function addPackListFields (form, options) {
  form.append('asn_code', options['asn-code'])
  form.append('source_type', options['source'] || 'UPLOAD')
  form.append('source_url', options['source-url'] || '')
  form.append('note', options.note || '')
  form.append('package_qty', options['package-qty'] || '0')
}

function packListForm (file, options) {
  const filePath = resolve(file)
  const fileInfo = statSync(filePath)
  if (!fileInfo.isFile()) throw new Error(`File not found: ${file}`)
  const form = new FormData()
  form.append(
    'file',
    new Blob([readFileSync(filePath)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
    basename(filePath)
  )
  addPackListFields(form, options)
  return form
}

function serialImportForm (file, options) {
  const filePath = resolve(file)
  const fileInfo = statSync(filePath)
  if (!fileInfo.isFile()) throw new Error(`File not found: ${file}`)
  const form = new FormData()
  form.append(
    'file',
    new Blob([readFileSync(filePath)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
    basename(filePath)
  )
  form.append('asn_code', options['asn-code'])
  form.append('mode', options.mode || 'receive')
  form.append('inbound_po', options['inbound-po'] || '')
  form.append('shipout_ref', options['shipout-ref'] || '')
  if (options['allow-all']) form.append('allow_all', 'true')
  return form
}

function print (payload, json) {
  process.stdout.write(json ? `${JSON.stringify(payload, null, 2)}\n` : `${payload.detail || 'success'}\n${JSON.stringify(payload, null, 2)}\n`)
}

function help () {
  process.stdout.write('Receiving acceptance: serial import --asn-code ASN --file FILE --mode receive --allow-all --dry-run|--confirm\n\n')
  process.stdout.write(`GreaterWMS CLI\n\nUsage:\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> list [--query JSON] [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> get --id ID [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> create --data JSON --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> update --id ID --data JSON --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> delete --id ID --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist list --asn-code ASN [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <operation> [--query JSON] [--json]\n\nResources:\n  warehouse, bin, bin-size, bin-property, sku, sku-unit, sku-class, sku-color,\n  sku-brand, sku-shape, sku-specs, sku-origin, supplier, customer, company, staff,\n  staff-types, driver, stock, asn, asn-detail, outbound, outbound-detail,\n  staging-slots, staging-assignments, dashboard-operations, dashboard-receipts,\n  dashboard-sales\n\nRead-only operations:\n  asn events | outbound picking-list | driver dispatch-list\n\nPack List operations:\n  packlist list --asn-code ASN\n  packlist import --asn-code ASN --file FILE --dry-run|--confirm\n  packlist confirm --id ID --confirm\n\nCommon options:\n  --query JSON       query parameters, for example '{"goods_code__icontains":"702"}'\n  --page N --page-size N\n  --id ID             record id for get/update/delete\n  --data JSON         JSON object for create/update\n  --data-file FILE    read create/update JSON from a file\n  --dry-run           print a write plan without changing data\n  --confirm           execute a previously reviewed write plan\n  --json              print machine-readable JSON\n\nEnvironment:\n  GREATERWMS_URL       GreaterWMS base URL (default: ${DEFAULT_URL})\n  GREATERWMS_TOKEN     authenticated openid token from the current GreaterWMS session\n  GREATERWMS_OPERATOR  optional staff id used for the audit operator\n  GREATERWMS_LANGUAGE  optional response language (default: en-US)\n\nMaster-data create/update and single-record delete require explicit confirmation. Pack List deletion and bulk cleanup are not supported.\n`)
}

async function main () {
  const { options, positional } = parseArgs(process.argv.slice(2))
  const [resource, action] = positional
  const json = Boolean(options.json)
  if (options.help || !resource || !action) {
    help()
    return
  }

  const operation = [resource, action].join(' ')
  if (await readAction(operation, options, json)) return
  if (await readResource(resource, action, options, json)) return
  if (await writeResource(resource, action, options, json)) return
  if (await deleteResource(resource, action, options, json)) return

  if (action === 'list') {
    if (resource === 'packlist') {
      if (!options['asn-code']) throw new Error('--asn-code is required')
      const query = `?asn_code=${encodeURIComponent(options['asn-code'])}`
      print(await request(`/asn/serial/packlists/${query}`), json)
      return
    }
    throw new Error(`Unknown read-only resource '${resource}'. Run --help to see supported resources.`)
  }

  if (resource === 'packlist' && action === 'import') {
    if (!options['asn-code']) throw new Error('--asn-code is required')
    if (!options.file) throw new Error('--file is required')
    if (!options['dry-run'] && !options.confirm) {
      throw new Error('Import is write-capable. Run --dry-run first, then repeat with --confirm.')
    }
    const form = packListForm(options.file, options)
    const endpoint = options['dry-run'] ? '/asn/serial/packlists/preview/' : '/asn/serial/packlists/import/'
    print(await request(endpoint, { method: 'POST', body: form }), json)
    return
  }

  if (resource === 'serial' && action === 'import') {
    if (!options['asn-code']) throw new Error('--asn-code is required')
    if (!options.file) throw new Error('--file is required')
    if (!['expected', 'receive'].includes(String(options.mode || 'receive').toLowerCase())) {
      throw new Error('--mode must be expected or receive')
    }
    requireConfirmation(options, 'serial import')
    if (options['dry-run']) {
      print({
        dry_run: true,
        method: 'POST',
        endpoint: '/asn/serial/import/',
        resource,
        action,
        asn_code: options['asn-code'],
        file: resolve(String(options.file)),
        mode: String(options.mode || 'receive').toLowerCase(),
        inbound_po: options['inbound-po'] || '',
        shipout_ref: options['shipout-ref'] || '',
        allow_all: Boolean(options['allow-all']),
      }, json)
      return
    }
    print(await request('/asn/serial/import/', { method: 'POST', body: serialImportForm(options.file, options) }), json)
    return
  }

  if (resource === 'packlist' && action === 'confirm') {
    if (!options.id) throw new Error('--id is required')
    if (!options.confirm) throw new Error('Confirmation is a write operation. Repeat with --confirm.')
    print(await request('/asn/serial/packlists/confirm/', { method: 'POST', json: { id: Number(options.id) } }), json)
    return
  }

  throw new Error(`Unknown command: ${operation}`)
}

main().catch(error => {
  process.stderr.write(`Error: ${error.message}\n`)
  process.exitCode = 1
})
