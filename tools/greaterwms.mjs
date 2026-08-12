#!/usr/bin/env node

import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  unlinkSync,
  writeFileSync
} from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'
import { homedir } from 'node:os'

const ENVIRONMENT_URLS = Object.freeze({
  production: 'https://maxsmartwms.online',
  test: 'https://greaterwms-v2-test3-sn.onrender.com'
})
const DEFAULT_ENVIRONMENT = 'production'
const DEFAULT_URL = ENVIRONMENT_URLS[DEFAULT_ENVIRONMENT]
let selectedUrl = null

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

function sessionFile () {
  if (process.env.GREATERWMS_SESSION_FILE) return resolve(process.env.GREATERWMS_SESSION_FILE)
  const configHome = process.env.XDG_CONFIG_HOME || join(homedir(), '.config')
  return join(configHome, 'greaterwms', 'session.json')
}

function loadSession () {
  try {
    const data = JSON.parse(readFileSync(sessionFile(), 'utf8'))
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {}
  } catch {
    return {}
  }
}

function saveSession (data) {
  const file = sessionFile()
  mkdirSync(dirname(file), { recursive: true, mode: 0o700 })
  writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, { mode: 0o600 })
  chmodSync(file, 0o600)
}

function normalizeUrl (value) {
  const url = String(value || '').trim().replace(/\/$/, '')
  if (!/^https?:\/\//i.test(url)) throw new Error('GreaterWMS URL must start with http:// or https://')
  return url
}

function environmentUrl (value) {
  const environment = String(value || '').trim().toLowerCase()
  if (!ENVIRONMENT_URLS[environment]) {
    throw new Error(`Unknown GreaterWMS environment '${value}'. Use production or test.`)
  }
  return ENVIRONMENT_URLS[environment]
}

function configureTarget (options) {
  if (options.url) {
    selectedUrl = normalizeUrl(options.url)
    return
  }
  if (options.env) {
    selectedUrl = environmentUrl(options.env)
    return
  }
  selectedUrl = null
}

function baseUrl () {
  if (selectedUrl) return selectedUrl
  if (process.env.GREATERWMS_URL) return normalizeUrl(process.env.GREATERWMS_URL)
  const session = loadSession()
  if (session.url) return normalizeUrl(session.url)
  return environmentUrl(process.env.GREATERWMS_ENV || DEFAULT_ENVIRONMENT)
}

function authHeaders () {
  const session = loadSession()
  const token = process.env.GREATERWMS_TOKEN || session.token
  if (!token) {
    throw new Error('GreaterWMS login required. Run: node tools/greaterwms.mjs login --env production')
  }
  if (!process.env.GREATERWMS_TOKEN && session.url && normalizeUrl(session.url) !== baseUrl()) {
    throw new Error(`Local session targets ${session.url}; current target is ${baseUrl()}. Run login --env for the selected environment.`)
  }
  return {
    token,
    operator: process.env.GREATERWMS_OPERATOR || session.operator || '',
    language: process.env.GREATERWMS_LANGUAGE || 'en-US'
  }
}

function readLine (prompt) {
  return new Promise((resolvePromise, reject) => {
    if (!process.stdin.isTTY || !process.stdout.isTTY) {
      reject(new Error(`${prompt.trim()} must be provided with an interactive terminal or environment variable`))
      return
    }
    process.stdout.write(prompt)
    const chunks = []
    const onData = (chunk) => {
      const value = String(chunk)
      for (const character of value) {
        if (character === '\u0003') {
          cleanup()
          reject(new Error('Input cancelled'))
          return
        }
        if (character === '\n' || character === '\r') {
          cleanup()
          resolvePromise(chunks.join(''))
          return
        }
        chunks.push(character)
      }
    }
    const cleanup = () => {
      process.stdin.off('data', onData)
      if (process.stdin.isRaw) process.stdin.setRawMode(false)
      process.stdin.pause()
      process.stdout.write('\n')
    }
    process.stdin.setRawMode(true)
    process.stdin.resume()
    process.stdin.on('data', onData)
  })
}

async function login (options, json) {
  const url = options.url ? normalizeUrl(options.url) : (options.env ? environmentUrl(options.env) : baseUrl())
  const name = options.name || process.env.GREATERWMS_USERNAME || await readLine('Admin name: ')
  const password = process.env.GREATERWMS_PASSWORD || await readLine('Password: ')
  if (!name || !password) throw new Error('Admin name and password are required')

  let response
  try {
    response = await fetch(`${url}/login/`, {
      method: 'POST',
      headers: { 'content-type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ name, password })
    })
  } catch (error) {
    throw new Error(`Unable to reach GreaterWMS at ${url}: ${error.message}`)
  }

  const text = await response.text()
  let payload
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    payload = { detail: text || response.statusText }
  }
  if (!response.ok || payload.code !== '200' || !payload.data?.openid) {
    const message = payload.msg || payload.detail || response.statusText || 'Login failed'
    throw new Error(`GreaterWMS login failed at ${url}: ${message}`)
  }

  saveSession({
    url,
    name: payload.data.name || name,
    operator: String(payload.data.user_id || ''),
    token: payload.data.openid,
    saved_at: new Date().toISOString()
  })
  print({ detail: 'login success', url, name: payload.data.name || name, operator: String(payload.data.user_id || ''), session_file: sessionFile() }, json)
}

function logout (json) {
  const file = sessionFile()
  const removed = existsSync(file)
  if (removed) unlinkSync(file)
  print({ detail: removed ? 'logout success' : 'no local session', session_file: file }, json)
}

function authStatus (json) {
  const session = loadSession()
  print({
    detail: session.token ? 'local session available' : 'login required',
    url: session.url || null,
    name: session.name || null,
    operator: session.operator || null,
    token_present: Boolean(session.token),
    session_file: sessionFile()
  }, json)
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
  form.append('note', options.note || '')
  form.append('package_qty', options['package-qty'] || '0')
  if (options.replace) form.append('replace', 'true')
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
  process.stdout.write('Authentication:\n  node tools/greaterwms.mjs login --env production --name ADMIN\n  node tools/greaterwms.mjs auth status\n  node tools/greaterwms.mjs logout\n  Password is prompted without echo and is never saved.\n\n')
  process.stdout.write('Exception review: serial exceptions --asn-code ASN; serial resolve --id ID --data JSON --dry-run|--confirm\n')
  process.stdout.write('Putaway: asn putaway --id ASN_DETAIL_ID --data JSON --dry-run|--confirm\n')
  process.stdout.write('  serial exceptions --asn-code ASN [--json]\n  serial resolve --id ID --data {"action":"ACCEPT_EXCEPTION","note":"QC approved"} --dry-run|--confirm\n  serial resolve-quantity --data {"asn_code":"ASN","goods_code":"SKU","action":"ACCEPT_EXCEPTION","note":"QC approved"} --dry-run|--confirm\n  asn putaway --id ASN_DETAIL_ID --data {"asn_code":"ASN","goods_code":"SKU","qty":1,"bin_name":"A1-01","putaway_driver":"Tom"} --dry-run|--confirm\n')
  process.stdout.write('Receiving acceptance: serial import --asn-code ASN --file FILE --mode receive --allow-all --dry-run|--confirm\n')
  process.stdout.write('Pack List replacement: add --replace after preview; replacement is blocked after physical receiving scans.\n\n')
  process.stdout.write(`GreaterWMS CLI\n\nUsage:\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> list [--query JSON] [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> get --id ID [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> create --data JSON --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> update --id ID --data JSON --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> delete --id ID --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist list --asn-code ASN [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <operation> [--query JSON] [--json]\n\nResources:\n  warehouse, bin, bin-size, bin-property, sku, sku-unit, sku-class, sku-color,\n  sku-brand, sku-shape, sku-specs, sku-origin, supplier, customer, company, staff,\n  staff-types, driver, stock, asn, asn-detail, outbound, outbound-detail,\n  staging-slots, staging-assignments, dashboard-operations, dashboard-receipts,\n  dashboard-sales\n\nRead-only operations:\n  asn events | outbound picking-list | driver dispatch-list\n\nPack List operations:\n  packlist list --asn-code ASN\n  packlist import --asn-code ASN --file FILE --dry-run|--confirm\n  packlist import --asn-code ASN --file FILE --replace --dry-run|--confirm\n  packlist confirm --id ID --confirm\n\nCommon options:\n  --query JSON       query parameters, for example '{"goods_code__icontains":"702"}'\n  --page N --page-size N\n  --id ID             record id for get/update/delete\n  --data JSON         JSON object for create/update\n  --data-file FILE    read create/update JSON from a file\n  --dry-run           print a write plan without changing data\n  --confirm           execute a previously reviewed write plan\n  --json              print machine-readable JSON\n\nEnvironment:\n  GREATERWMS_URL       GreaterWMS base URL (default: ${DEFAULT_URL})\n  GREATERWMS_TOKEN     authenticated openid token from the current GreaterWMS session\n  GREATERWMS_OPERATOR  optional staff id used for the audit operator\n  GREATERWMS_LANGUAGE  optional response language (default: en-US)\n\nMaster-data create/update and single-record delete require explicit confirmation. Pack List deletion and bulk cleanup are not supported.\n`)
}

async function main () {
  const { options, positional } = parseArgs(process.argv.slice(2))
  const [resource, action] = positional
  const json = Boolean(options.json)
  if (options.help || !resource || (!action && !['login', 'logout'].includes(resource))) {
    help()
    return
  }

  configureTarget(options)
  if (resource === 'login') {
    await login(options, json)
    return
  }
  if (resource === 'logout') {
    logout(json)
    return
  }
  if (resource === 'auth' && action === 'login') {
    await login(options, json)
    return
  }
  if (resource === 'auth' && action === 'logout') {
    logout(json)
    return
  }
  if (resource === 'auth' && action === 'status') {
    authStatus(json)
    return
  }

  const operation = [resource, action].join(' ')
  if (resource === 'serial' && action === 'exceptions') {
    if (!options['asn-code']) throw new Error('--asn-code is required')
    print(await request(`/asn/serial/exceptions/?asn_code=${encodeURIComponent(options['asn-code'])}`), json)
    return
  }

  if (resource === 'serial' && action === 'resolve') {
    if (!options.id) throw new Error('--id is required')
    requireConfirmation(options, 'serial resolve')
    const data = parseData(options)
    if (options['dry-run']) {
      print({ dry_run: true, method: 'POST', endpoint: '/asn/serial/exceptions/resolve/', resource, action, id: String(options.id), data }, json)
      return
    }
    print(await request('/asn/serial/exceptions/resolve/', {
      method: 'POST',
      json: { ...data, id: Number(options.id) }
    }), json)
    return
  }

  if (resource === 'serial' && action === 'resolve-quantity') {
    requireConfirmation(options, 'serial resolve-quantity')
    const data = parseData(options)
    if (options['dry-run']) {
      print({ dry_run: true, method: 'POST', endpoint: '/asn/serial/exceptions/resolve-quantity/', resource, action, data }, json)
      return
    }
    print(await request('/asn/serial/exceptions/resolve-quantity/', { method: 'POST', json: data }), json)
    return
  }

  if (resource === 'asn' && action === 'putaway') {
    if (!options.id) throw new Error('--id is required')
    requireConfirmation(options, 'asn putaway')
    const data = parseData(options)
    const endpoint = `/asn/movetobin/${encodeURIComponent(String(options.id))}/`
    if (options['dry-run']) {
      print({ dry_run: true, method: 'POST', endpoint, resource, action, id: String(options.id), data }, json)
      return
    }
    print(await request(endpoint, { method: 'POST', json: data }), json)
    return
  }

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
