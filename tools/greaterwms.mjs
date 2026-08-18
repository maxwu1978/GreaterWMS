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
import { randomUUID } from 'node:crypto'
import { basename, dirname, join, resolve } from 'node:path'
import { homedir } from 'node:os'

const ENVIRONMENT_URLS = Object.freeze({
  // The production web app is served by the frontend domain; CLI requests
  // must target the API origin directly.
  production: 'https://api.maxsmartwms.online',
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
  'dashboard-sales': '/dashboard/sales/',
  receiving: '/receiving/records/',
  transport: '/transport/orders/'
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
  'dashboard-sales',
  'receiving',
  'transport'
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
  const surface = String(process.env.GREATERWMS_AGENT_SURFACE || 'cli').toLowerCase()
  return {
    token,
    operator: process.env.GREATERWMS_OPERATOR || session.operator || '',
    language: process.env.GREATERWMS_LANGUAGE || 'en-US',
    'x-agent-client': surface === 'ai' ? 'greaterwms-ai' : 'greaterwms-cli',
    'x-agent-surface': surface
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
  const isStaff = Boolean(options.staff)
  const name = options.name || process.env.GREATERWMS_USERNAME || await readLine(isStaff ? 'Staff name: ' : 'Admin name: ')
  const credential = isStaff
    ? (options['check-code'] || process.env.GREATERWMS_CHECK_CODE || await readLine('Check code: '))
    : (options.password || process.env.GREATERWMS_PASSWORD || await readLine('Password: '))
  if (!name || !credential) {
    throw new Error(isStaff ? 'Staff name and check code are required' : 'Admin name and password are required')
  }

  let response
  try {
    response = await fetch(`${url}${isStaff ? '/staff/login/' : '/login/'}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json; charset=utf-8' },
      body: JSON.stringify(isStaff
        ? { staff_name: name, check_code: credential }
        : { name, password: credential })
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
  const token = payload.data?.token || payload.data?.openid
  if (!response.ok || payload.code !== '200' || !token) {
    const message = payload.msg || payload.detail || response.statusText || 'Login failed'
    throw new Error(`GreaterWMS ${isStaff ? 'staff ' : ''}login failed at ${url}: ${message}`)
  }

  saveSession({
    url,
    name: payload.data.name || name,
    operator: String(payload.data.user_id || ''),
    role: payload.data.staff_type || (isStaff ? 'Staff' : 'Admin'),
    login_mode: isStaff ? 'staff' : 'admin',
    token,
    saved_at: new Date().toISOString()
  })
  print({
    detail: `${isStaff ? 'staff ' : ''}login success`,
    url,
    name: payload.data.name || name,
    role: payload.data.staff_type || (isStaff ? 'Staff' : 'Admin'),
    operator: String(payload.data.user_id || ''),
    session_file: sessionFile()
  }, json)
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
    role: session.role || null,
    login_mode: session.login_mode || null,
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
  const timeoutMs = Number(process.env.GREATERWMS_TIMEOUT_MS || options.timeoutMs || 30000)
  const response = await fetch(`${baseUrl()}${path}`, {
    method: options.method || 'GET',
    headers,
    body,
    signal: AbortSignal.timeout(timeoutMs)
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

async function publicRequest (path, url) {
  const response = await fetch(`${url}${path}`, {
    method: 'GET',
    headers: { accept: 'application/json' },
    signal: AbortSignal.timeout(30000)
  })
  const text = await response.text()
  let payload
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    payload = { detail: text || response.statusText }
  }
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload)
    throw new Error(`HTTP ${response.status}: ${detail}`)
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
  let value = options.data
  if (options['data-file']) {
    const file = String(options['data-file'])
    try {
      value = readFileSync(resolve(file), 'utf8')
    } catch {
      throw new Error(`File not found: ${file}`)
    }
  }
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

function agentConfirmationHeaders (options, label) {
  if (!options.confirm) throw new Error(`${label} requires --confirm after reviewing the server preview.`)
  const token = options['confirmation-token'] || options['confirm-token']
  if (!token) throw new Error(`${label} requires --confirmation-token from the server preview.`)
  return {
    'confirmation-token': String(token),
    'idempotency-key': String(options['idempotency-key'] || randomUUID())
  }
}

async function agentPreview (operation, payload, options = {}) {
  return request('/asn/serial/agent/preview/', {
    method: 'POST',
    headers: { 'x-agent-preview': 'true' },
    json: {
      operation,
      resource_id: options.resourceId ? String(options.resourceId) : '',
      asn_code: options.asnCode ? String(options.asnCode) : '',
      source_evidence_id: options.sourceEvidenceId || options['source-evidence-id'] || '',
      payload
    }
  })
}

function agentPayload (data) {
  return data && typeof data === 'object' ? data : {}
}

async function runAgentJsonCommand ({ operation, endpoint, method = 'POST', data, options, json, resourceId = '', asnCode = '' }) {
  if (options['dry-run']) {
    print(await agentPreview(operation, agentPayload(data), {
      resourceId,
      asnCode,
      sourceEvidenceId: options['source-evidence-id'] || '',
    }), json)
    return
  }
  if (String(process.env.GREATERWMS_AGENT_SURFACE || '').toLowerCase() === 'ai') {
    throw new Error('AI surface requires the structured approval action: run agent approve --id PREVIEW_ID. CLI confirmation tokens remain available on the default CLI surface.')
  }
  print(await request(endpoint, {
    method,
    headers: agentConfirmationHeaders(options, operation),
    json: agentPayload(data)
  }), json)
}

async function runProtectedJsonCommand ({ operation, endpoint, method = 'POST', data, options, json }) {
  requireConfirmation(options, operation)
  if (options['dry-run']) {
    print({ dry_run: true, method, endpoint, operation, data }, json)
    return
  }
  print(await request(endpoint, { method, json: agentPayload(data) }), json)
}

function validateOutboundCreateData (data) {
  if (!data.customer) throw new Error('outbound create requires customer in --data')
  if (!data.creater) throw new Error('outbound create requires creater in --data')
  return data
}

function validateOutboundDetailData (data) {
  if (!data.dn_code) throw new Error('outbound-detail create requires dn_code in --data')
  if (!Array.isArray(data.goods_code) || data.goods_code.length === 0) {
    throw new Error('outbound-detail create requires goods_code as a non-empty JSON array')
  }
  if (!Array.isArray(data.goods_qty) || data.goods_qty.length === 0) {
    throw new Error('outbound-detail create requires goods_qty as a non-empty JSON array')
  }
  if (data.goods_code.length !== data.goods_qty.length) {
    throw new Error('outbound-detail create requires goods_code and goods_qty arrays with the same length')
  }
  return data
}

function validateReceivingCreateData (data) {
  if (!Array.isArray(data.staging_bins) || data.staging_bins.length === 0) {
    throw new Error('receiving create requires staging_bins with at least one Stage-left/Stage-right slot')
  }
  return data
}

async function readResource (resource, action, options, json) {
  if (resource === 'receiving' && !['list', 'get'].includes(action)) return false
  if (resource === 'transport' && !['list', 'get'].includes(action)) return false
  if (resource === 'sku' && action === 'import') return false
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
  if (resource === 'sku' && action === 'import') {
    requireConfirmation(options, 'sku source import')
    const data = parseData(options)
    if (!data.source_evidence_id && !data.items?.every(item => item.source_evidence_id)) {
      throw new Error('sku import requires source_evidence_id in --data or on every item')
    }
    if (options['dry-run']) {
      print({
        dry_run: true,
        method: 'POST',
        endpoint: '/goods/import/',
        resource,
        action,
        data
      }, json)
      return true
    }
    print(await request('/goods/import/', { method: 'POST', json: data }), json)
    return true
  }
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
  form.append('source_type', options['source'] || 'AI_AGENT')
  form.append('note', options.note || '')
  form.append('package_qty', options['package-qty'] || '0')
  if (options.replace) form.append('replace', 'true')
  if (options['late-reference']) form.append('late_reference', 'true')
}

function packListForm (file, options) {
  const filePath = resolve(file)
  let fileInfo
  try {
    fileInfo = statSync(filePath)
  } catch {
    throw new Error(`File not found: ${file}`)
  }
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
  let fileInfo
  try {
    fileInfo = statSync(filePath)
  } catch {
    throw new Error(`File not found: ${file}`)
  }
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
  form.append('source_type', options.source || 'AI_AGENT')
  form.append('note', options.note || '')
  form.append('evidence_url', options['evidence-url'] || '')
  if (options['allow-all']) form.append('allow_all', 'true')
  return form
}

function print (payload, json) {
  process.stdout.write(json ? `${JSON.stringify(payload, null, 2)}\n` : `${payload.detail || 'success'}\n${JSON.stringify(payload, null, 2)}\n`)
}

function recoveryHint (message, operation = '') {
  const text = `${operation} ${message}`.toLowerCase()
  if (text.includes('dry-run') || text.includes('dry run')) {
    return 'Run the same write command with --dry-run --json, review the server preview, then repeat with --confirm and its confirmation token.'
  }
  if (text.includes('confirmation-token') || text.includes('confirmation token')) {
    return 'Use the confirmation_token returned by the latest dry-run preview and provide a stable --idempotency-key.'
  }
  if (text.includes('login required') || text.includes('invalid or revoked token') || text.includes('token expired')) {
    return 'Log in for the selected environment, then rerun: node tools/greaterwms.mjs login --env production.'
  }
  if (text.includes('asn create requires')) {
    return 'Provide a trusted supplier or container_tracking reference, then preview the ASN before confirming it.'
  }
  if (text.includes('asn detail create requires')) {
    return 'Provide the existing ASN code in --data or --data-file; do not create a second ASN for the same load.'
  }
  if (text.includes('outbound create requires customer')) {
    return 'Provide the exact customer or owner from the customer order, then run outbound create with --dry-run.'
  }
  if (text.includes('outbound create requires creater')) {
    return 'Provide the authenticated warehouse operator as creater, then run outbound create with --dry-run.'
  }
  if (text.includes('outbound-detail create requires')) {
    return 'Provide dn_code, goods_code, and goods_qty as matching arrays, then preview the outbound detail.'
  }
  if (text.includes('--id is required')) {
    return 'Use a read-only list/get command to find the existing record id, then rerun the operation with --id.'
  }
  if (text.includes('file not found') || text.includes('enoent')) {
    return 'Provide an existing input file path and rerun the preview. No import or outbound record was created.'
  }
  if (text.includes('requires asn status 3')) {
    return 'Complete physical arrival and unloading first, then finish unloading so the ASN reaches Receiving before submitting received quantities.'
  }
  if (text.includes('mark the asn as arrived') || text.includes('physical arrival')) {
    return 'Confirm the vehicle has physically arrived with asn arrival, then preview unload-start again. No staging slot is occupied by this rejection.'
  }
  if (text.includes('not ready for putaway') || text.includes('putaway')) {
    return 'Check that receiving/QC is complete, accepted quantity remains, all exceptions are resolved, and the assigned driver and final storage bin are valid.'
  }
  if (text.includes('pack list') || text.includes('packlist')) {
    return 'Check packlist list, correct the workbook mapping, then preview packlist import. Use --late-reference only after receiving has started.'
  }
  if (text.includes('sku does not exist') || text.includes('goods code does not exist')) {
    return 'List the tenant SKU master data, create or import the missing SKU, then rerun ASN detail create from a fresh preview.'
  }
  if (text.includes('delivery details') || text.includes('exception note') || text.includes('delivery actual')) {
    return 'Submit one POD line for every shipped SKU. If actual quantity differs or damage is present, include a delivery note before confirming.'
  }
  if (text.includes('cancellation reason')) {
    return 'Provide a clear cancellation_note, then confirm whether the goods returned to the warehouse; returned goods must use the OUTBOUND_RETURN receiving flow.'
  }
  if (text.includes('stock is insufficient') || text.includes('insufficient stock')) {
    return 'Check available stock, picked quantity, and the requested SKU or SN before releasing the order again.'
  }
  if (text.includes('dn status') || text.includes('delivery note') || text.includes('outbound')) {
    return 'Read the delivery note and picking list, then follow the required sequence: release, order-release, pick, dispatch, and POD or cancel-intransit.'
  }
  if (/(^|\s)(serial|sn)(\s|$)/.test(text)) {
    return 'Review serial exceptions or inspection results first. Resolve the exception with a note and required location before putaway.'
  }
  if (text.includes('staging') || text.includes('stage-left') || text.includes('stage-right')) {
    return 'List staging-slots, verify package/load-unit capacity, reserve valid Stage-left or Stage-right slots, and do not occupy them before physical unloading.'
  }
  if (text.includes('driver')) {
    return 'List driver records and use an active driver assigned to this task. Do not start unloading or putaway without the required driver.'
  }
  if (text.includes('arrival') || text.includes('unloading')) {
    return 'Check ASN state and event history. Mark actual arrival first; unloading is blocked until the vehicle has physically arrived.'
  }
  if (text.includes('permission') || text.includes('forbidden') || text.includes('403')) {
    return 'Use the CLI with the warehouse role that owns this step. QC handles inspection and exceptions; drivers do not receive administrative write access.'
  }
  if (text.includes('not found') || text.includes('does not exist')) {
    return 'Verify tenant, warehouse, ASN id/code, SKU, driver, and bin with read-only list/get commands before retrying.'
  }
  return 'Inspect the current ASN, Pack List, staging assignments, exceptions, and event history; follow the returned business status before retrying.'
}

function help () {
  process.stdout.write('Authentication:\n  node tools/greaterwms.mjs login --env production --name ADMIN\n  node tools/greaterwms.mjs login --env production --staff --name STAFF\n  node tools/greaterwms.mjs auth status\n  node tools/greaterwms.mjs logout\n  Password/check code is prompted without echo and is never saved.\n\n')
  process.stdout.write('Installation: node tools/greaterwms.mjs install-info --env production --json\n\n')
  process.stdout.write('Inbound: asn eta|arrival|reserve-staging|unload-start|unload-finish|receive --id ID --data JSON --dry-run|--confirm\n')
  process.stdout.write('Exception review: serial exceptions --asn-code ASN; serial resolve --id ID --data JSON --dry-run|--confirm\n')
  process.stdout.write('Putaway: asn putaway|putaway-bulk --id ID --data JSON --dry-run|--confirm\n')
  process.stdout.write('  serial exceptions --asn-code ASN [--json]\n  serial resolve --id ID --data {"action":"REPAIR_REWORK","note":"Needs repair and reinspection","resolution_location":"REPAIR-01"} --dry-run|--confirm\n  serial resolve --id ID --data {"action":"ACCEPT_FOR_PUTAWAY","note":"Passed reinspection"} --dry-run|--confirm\n  serial resolve-quantity --data {"asn_code":"ASN","goods_code":"SKU","action":"ACCEPT_EXCEPTION","note":"QC approved"} --dry-run|--confirm\n  asn putaway --id ASN_DETAIL_ID --data {"asn_code":"ASN","goods_code":"SKU","qty":1,"bin_name":"A1-01","putaway_driver":"Tom"} --dry-run|--confirm\n')
  process.stdout.write('AI Agent/CLI ingestion: Pack List and QC imports are not available in the web page.\n')
  process.stdout.write('QC inspection: inspection import --asn-code ASN --file FILE [--evidence-url URL] --allow-all --dry-run|--confirm; inspection list --asn-code ASN\n')
  process.stdout.write('Receiving: receiving create|staging-assign|qc|resolve|putaway|reconcile|resolve-reconciliation --data JSON --dry-run|--confirm; receiving exceptions\n')
  process.stdout.write('Transport: transport create|assign|transition --data JSON --dry-run|--confirm; transport list\n')
  process.stdout.write('Outbound: outbound create; outbound-detail create; outbound release|order-release|pick|dispatch|pod|cancel-intransit --id ID --data JSON --dry-run|--confirm\n')
  process.stdout.write('Source intake: source sync-state --mailbox-account EMAIL; source sync-start --mailbox-account EMAIL; source capture --data JSON --json; source intake [--status STATUS] [--operation INBOUND|OUTBOUND] [--json]\n')
  process.stdout.write('Source SKU import: sku import --data-file /tmp/sku-import.json --dry-run|--confirm --json; requires source_evidence_id and accepts blank optional master-data fields.\n')
  process.stdout.write('Source detail/update: source intake-get --id ID; source intake-update --id ID --data JSON --dry-run|--confirm; source sync-finish --id RUN_ID --data JSON\n')
  process.stdout.write('AI approval: GREATERWMS_AGENT_SURFACE=ai node tools/greaterwms.mjs agent approve --id PREVIEW_ID --json\n')
  process.stdout.write('AI surface: set GREATERWMS_AGENT_SURFACE=ai, preview with --source-evidence-id SOURCE_ID, then approve with agent approve --id PREVIEW_ID. No CLI token is exposed on this surface.\n')
  process.stdout.write('Late Pack List: add --replace --late-reference after preview; the prior Pack List and receiving history remain preserved.\n\n')
  process.stdout.write('QC inspection operations: inspection list --asn-code ASN; inspection import --asn-code ASN --file FILE --allow-all --dry-run|--confirm\n')
  process.stdout.write('CLI compatibility writes use --confirmation-token TOKEN_FROM_PREVIEW and --idempotency-key KEY. AI writes use structured agent approve and do not use tokens.\n')
  process.stdout.write('Tenant cleanup: tenant cleanup --dry-run, then tenant cleanup --confirm with the preview token.\n')
  process.stdout.write('Inbound CLI test suite: node tools/inbound-cli-test-suite.mjs [--catalog|--live --env test --asn-id ID --asn-code ASN]\n')
  process.stdout.write('Outbound CLI test suite: node tools/outbound-cli-test-suite.mjs [--catalog|--live --env test --dn-id ID --dn-code DN]\n')
  process.stdout.write(`GreaterWMS CLI\n\nUsage:\n  node tools/greaterwms.mjs login --env production --name ADMIN\n  node tools/greaterwms.mjs login --env production --staff --name STAFF\n  node tools/greaterwms.mjs install-info --env production --json\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> list [--query JSON] [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> get --id ID [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> create --data JSON --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> update --id ID --data JSON --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <resource> delete --id ID --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist list --asn-code ASN [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs <operation> [--query JSON] [--json]\n\nResources:\n  warehouse, bin, bin-size, bin-property, sku, sku-unit, sku-class, sku-color,\n  sku-brand, sku-shape, sku-specs, sku-origin, supplier, customer, company, staff,\n  staff-types, driver, stock, asn, asn-detail, outbound, outbound-detail,\n  staging-slots, staging-assignments, dashboard-operations, dashboard-receipts,\n  dashboard-sales\n\nRead-only operations:\n  asn events | outbound picking-list | driver dispatch-list\n\nPack List operations:\n  packlist list --asn-code ASN\n  packlist import --asn-code ASN --file FILE --dry-run|--confirm\n  packlist import --asn-code ASN --file FILE --replace --dry-run|--confirm\n  packlist confirm --id ID --confirm\n\nCommon options:\n  --query JSON       query parameters, for example '{"goods_code__icontains":"702"}'\n  --page N --page-size N\n  --id ID             record id for get/update/delete\n  --data JSON         JSON object for create/update\n  --data-file FILE    read create/update JSON from a file\n  --dry-run           print a write plan without changing data\n  --confirm           execute a previously reviewed write plan\n  --json              print machine-readable JSON\n\nEnvironment:\n  GREATERWMS_URL       GreaterWMS base URL (default: ${DEFAULT_URL})\n  GREATERWMS_TOKEN     authenticated session token override\n  GREATERWMS_CHECK_CODE staff check code for non-interactive staff login\n  GREATERWMS_OPERATOR  optional staff id used for the audit operator\n  GREATERWMS_LANGUAGE  optional response language (default: en-US)\n\nMaster-data create/update and single-record delete require explicit confirmation. Pack List deletion and bulk cleanup are not supported.\n`)
}

async function main () {
  const { options, positional } = parseArgs(process.argv.slice(2))
  const [resource, action] = positional
  const json = Boolean(options.json)
  if (options.help || !resource || (!action && !['login', 'logout', 'install-info'].includes(resource))) {
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
  if (resource === 'install-info' || (resource === 'auth' && action === 'install-info')) {
    print(await publicRequest('/cli/install/', baseUrl()), json)
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

  if (resource === 'agent' && action === 'approve') {
    if (!options.id) throw new Error('--id is required for agent approve')
    if (String(process.env.GREATERWMS_AGENT_SURFACE || '').toLowerCase() !== 'ai') {
      throw new Error('agent approve is only available on GREATERWMS_AGENT_SURFACE=ai; use the legacy CLI confirmation token flow on the default surface.')
    }
    print(await request(`/asn/serial/agent/preview/${encodeURIComponent(String(options.id))}/approve/`, {
      method: 'POST',
      json: {}
    }), json)
    return
  }

  if (resource === 'source' && action === 'capture') {
    const data = parseData(options)
    print(await request('/asn/serial/sources/capture/', {
      method: 'POST',
      json: data
    }), json)
    return
  }

  if (resource === 'source' && action === 'list') {
    const params = new URLSearchParams()
    for (const [option, queryName] of [
      ['operation', 'operation'],
      ['mailbox-account', 'mailbox_account'],
      ['message-id', 'message_id'],
      ['content-hash', 'content_hash']
    ]) {
      if (options[option]) params.set(queryName, String(options[option]))
    }
    const suffix = params.toString() ? `?${params.toString()}` : ''
    print(await request(`/asn/serial/sources/${suffix}`), json)
    return
  }

  if (resource === 'source' && action === 'intake') {
    print(await request(queryPath('/asn/serial/intake/', options)), json)
    return
  }

  if (resource === 'source' && action === 'intake-get') {
    if (!options.id) throw new Error('--id is required for source intake-get')
    print(await request(`/asn/serial/intake/${encodeURIComponent(String(options.id))}/`), json)
    return
  }

  if (resource === 'source' && action === 'intake-update') {
    if (!options.id) throw new Error('--id is required for source intake-update')
    const data = parseData(options)
    if (options['dry-run']) {
      print({
        dry_run: true,
        method: 'POST',
        endpoint: `/asn/serial/intake/${encodeURIComponent(String(options.id))}/update/`,
        data
      }, json)
      return
    }
    if (!options.confirm) throw new Error('source intake-update requires --confirm after reviewing the source record')
    print(await request(`/asn/serial/intake/${encodeURIComponent(String(options.id))}/update/`, {
      method: 'POST',
      json: data
    }), json)
    return
  }

  if (resource === 'source' && action === 'sync-start') {
    const data = parseData(options)
    if (!data.mailbox_account) data.mailbox_account = options['mailbox-account']
    if (!data.mailbox_account) throw new Error('source sync-start requires --mailbox-account or mailbox_account in --data')
    print(await request('/asn/serial/intake/sync-runs/', {
      method: 'POST',
      json: data
    }), json)
    return
  }

  if (resource === 'source' && action === 'sync-state') {
    const mailboxAccount = options['mailbox-account'] || parseData(options).mailbox_account
    if (!mailboxAccount) throw new Error('source sync-state requires --mailbox-account or mailbox_account in --data')
    print(await request(`/asn/serial/intake/sync-state/?mailbox_account=${encodeURIComponent(String(mailboxAccount))}`), json)
    return
  }

  if (resource === 'source' && action === 'sync-finish') {
    if (!options.id) throw new Error('--id is required for source sync-finish')
    const data = parseData(options)
    print(await request(`/asn/serial/intake/sync-runs/${encodeURIComponent(String(options.id))}/complete/`, {
      method: 'POST',
      json: data
    }), json)
    return
  }

  if (resource === 'tenant' && action === 'cleanup') {
    requireConfirmation(options, 'tenant cleanup')
    if (options['dry-run']) {
      print(await request('/tenant/cleanup/preview/', {
        method: 'POST',
        headers: { 'x-agent-preview': 'true' },
        json: {}
      }), json)
    } else {
      print(await request('/tenant/cleanup/', {
        method: 'POST',
        headers: agentConfirmationHeaders(options, 'tenant cleanup'),
        json: {}
      }), json)
    }
    return
  }

  const operation = [resource, action].join(' ')

  if (resource === 'asn' && action === 'create') {
    const data = parseData(options)
    if (!data.supplier && !data.container_tracking) throw new Error('ASN create requires at least supplier or container_tracking in --data')
    requireConfirmation(options, 'asn create')
    await runAgentJsonCommand({
      operation: 'asn.create',
      endpoint: '/asn/list/',
      data,
      options,
      json
    })
    return
  }

  if (resource === 'asn-detail' && action === 'create') {
    const data = parseData(options)
    if (!data.asn_code) throw new Error('ASN detail create requires asn_code in --data')
    requireConfirmation(options, 'asn-detail create')
    await runAgentJsonCommand({
      operation: 'asn.detail.create',
      endpoint: '/asn/detail/',
      data,
      options,
      json,
      asnCode: data.asn_code
    })
    return
  }

  const inboundActions = {
    eta: { operation: 'asn.eta', path: (id) => `/asn/eta/${encodeURIComponent(String(id))}/` },
    arrival: { operation: 'asn.arrival', path: (id) => `/asn/arrival/${encodeURIComponent(String(id))}/` },
    'reserve-staging': { operation: 'asn.reserve_staging', path: (id) => `/asn/reserve-staging/${encodeURIComponent(String(id))}/` },
    'unload-start': { operation: 'asn.unload_start', path: (id) => `/asn/preload/${encodeURIComponent(String(id))}/` },
    'unload-finish': { operation: 'asn.unload_finish', path: (id) => `/asn/presort/${encodeURIComponent(String(id))}/` },
    receive: { operation: 'asn.receive', path: (id) => `/asn/sorted/${encodeURIComponent(String(id))}/` }
  }
  if (resource === 'asn' && inboundActions[action]) {
    if (!options.id) throw new Error('--id is required')
    const data = parseData(options)
    const asnCode = options['asn-code'] || data.asn_code || ''
    if (['receive', 'reserve-staging', 'unload-start', 'unload-finish'].includes(action) && !asnCode) {
      throw new Error('--asn-code or asn_code in --data is required')
    }
    requireConfirmation(options, `asn ${action}`)
    await runAgentJsonCommand({
      operation: inboundActions[action].operation,
      endpoint: inboundActions[action].path(options.id),
      data,
      options,
      json,
      resourceId: options.id,
      asnCode
    })
    return
  }

  if (resource === 'asn' && action === 'putaway-bulk') {
    const data = parseData(options)
    const asnCode = options['asn-code'] || data.asn_code || ''
    if (!asnCode) throw new Error('--asn-code or asn_code in --data is required')
    requireConfirmation(options, 'asn putaway-bulk')
    await runAgentJsonCommand({
      operation: 'asn.putaway_bulk',
      endpoint: '/asn/movetobin/',
      method: 'PUT',
      data,
      options,
      json,
      resourceId: asnCode,
      asnCode
    })
    return
  }

  if (resource === 'serial' && action === 'exceptions') {
    if (!options['asn-code']) throw new Error('--asn-code is required')
    print(await request(`/asn/serial/exceptions/?asn_code=${encodeURIComponent(options['asn-code'])}`), json)
    return
  }

  if (resource === 'inspection' && action === 'list') {
    if (!options['asn-code']) throw new Error('--asn-code is required')
    print(await request(`/asn/serial/inspections/?asn_code=${encodeURIComponent(options['asn-code'])}`), json)
    return
  }

  if (resource === 'serial' && action === 'resolve') {
    if (!options.id) throw new Error('--id is required')
    requireConfirmation(options, 'serial resolve')
    const data = parseData(options)
    const payload = { ...data, id: Number(options.id) }
    await runAgentJsonCommand({
      operation: 'serial.resolve',
      endpoint: '/asn/serial/exceptions/resolve/',
      data: payload,
      options,
      json,
      resourceId: options.id,
      asnCode: data.asn_code || ''
    })
    return
  }

  if (resource === 'serial' && action === 'resolve-quantity') {
    requireConfirmation(options, 'serial resolve-quantity')
    const data = parseData(options)
    await runAgentJsonCommand({
      operation: 'serial.resolve_quantity',
      endpoint: '/asn/serial/exceptions/resolve-quantity/',
      data,
      options,
      json,
      resourceId: `${data.asn_code || ''}:${data.goods_code || ''}`,
      asnCode: data.asn_code || ''
    })
    return
  }

  if (resource === 'serial' && action === 'exception-move') {
    if (!options.id) throw new Error('--id is required')
    requireConfirmation(options, 'serial exception-move')
    const data = parseData(options)
    const payload = { ...data, id: Number(options.id) }
    await runAgentJsonCommand({
      operation: 'serial.exception_move',
      endpoint: '/asn/serial/exceptions/move/',
      data: payload,
      options,
      json,
      resourceId: options.id,
      asnCode: options['asn-code'] || data.asn_code || ''
    })
    return
  }

  if (resource === 'serial' && action === 'exception-move-quantity') {
    requireConfirmation(options, 'serial exception-move-quantity')
    const data = parseData(options)
    await runAgentJsonCommand({
      operation: 'serial.exception_move_quantity',
      endpoint: '/asn/serial/exceptions/move-quantity/',
      data,
      options,
      json,
      resourceId: `${data.asn_code || ''}:${data.goods_code || ''}`,
      asnCode: data.asn_code || ''
    })
    return
  }

  if (resource === 'asn' && action === 'putaway') {
    if (!options.id) throw new Error('--id is required')
    requireConfirmation(options, 'asn putaway')
    const data = parseData(options)
    const endpoint = `/asn/movetobin/${encodeURIComponent(String(options.id))}/`
    await runAgentJsonCommand({
      operation: 'asn.putaway',
      endpoint,
      data,
      options,
      json,
      resourceId: options.id,
      asnCode: data.asn_code || ''
    })
    return
  }

  const outboundActions = {
    release: { operation: 'outbound.release', endpoint: (id) => `/dn/neworder/${encodeURIComponent(String(id))}/`, method: 'POST' },
    'order-release': { operation: 'outbound.order_release', endpoint: (id) => `/dn/orderrelease/${encodeURIComponent(String(id))}/`, method: 'PUT' },
    pick: { operation: 'outbound.pick', endpoint: (id) => `/dn/picked/${encodeURIComponent(String(id))}/`, method: 'POST' },
    dispatch: { operation: 'outbound.dispatch', endpoint: (id) => `/dn/dispatch/${encodeURIComponent(String(id))}/`, method: 'POST' },
    pod: { operation: 'outbound.pod', endpoint: (id) => `/dn/pod/${encodeURIComponent(String(id))}/`, method: 'POST' },
    'cancel-intransit': { operation: 'outbound.cancel_intransit', endpoint: (id) => `/dn/cancel-intransit/${encodeURIComponent(String(id))}/`, method: 'POST' },
  }
  if (resource === 'outbound' && action === 'create') {
    const data = validateOutboundCreateData(parseData(options))
    requireConfirmation(options, 'outbound create')
    await runAgentJsonCommand({
      operation: 'outbound.create',
      endpoint: '/dn/list/',
      data,
      options,
      json,
    })
    return
  }
  if (resource === 'outbound-detail' && action === 'create') {
    const data = validateOutboundDetailData(parseData(options))
    requireConfirmation(options, 'outbound-detail create')
    await runAgentJsonCommand({
      operation: 'outbound.detail.create',
      endpoint: '/dn/detail/',
      data,
      options,
      json,
      resourceId: data.dn_code,
    })
    return
  }
  if (resource === 'outbound' && outboundActions[action]) {
    if (!options.id) throw new Error('--id is required')
    const data = parseData(options)
    requireConfirmation(options, `outbound ${action}`)
    const definition = outboundActions[action]
    await runAgentJsonCommand({
      operation: definition.operation,
      endpoint: definition.endpoint(options.id),
      method: definition.method,
      data,
      options,
      json,
      resourceId: options.id,
    })
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
    const headers = options['dry-run'] ? {} : agentConfirmationHeaders(options, 'packlist import')
    print(await request(endpoint, { method: 'POST', headers, body: form }), json)
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
      print(await request('/asn/serial/import/preview/', {
        method: 'POST',
        headers: { 'x-agent-preview': 'true' },
        body: serialImportForm(options.file, options)
      }), json)
      return
    }
    print(await request('/asn/serial/import/', {
      method: 'POST',
      headers: agentConfirmationHeaders(options, 'serial import'),
      body: serialImportForm(options.file, options)
    }), json)
    return
  }

  if (resource === 'inspection' && action === 'import') {
    if (!options['asn-code']) throw new Error('--asn-code is required')
    if (!options.file) throw new Error('--file is required')
    requireConfirmation(options, 'inspection import')
    const inspectionOptions = { ...options, mode: 'receive' }
    if (options['dry-run']) {
      print(await request('/asn/serial/inspections/preview/', {
        method: 'POST',
        headers: { 'x-agent-preview': 'true' },
        body: serialImportForm(options.file, inspectionOptions)
      }), json)
      return
    }
    print(await request('/asn/serial/inspections/import/', {
      method: 'POST',
      headers: agentConfirmationHeaders(options, 'inspection import'),
      body: serialImportForm(options.file, inspectionOptions)
    }), json)
    return
  }

  if (resource === 'packlist' && action === 'confirm') {
    if (!options.id) throw new Error('--id is required')
    requireConfirmation(options, 'packlist confirm')
    const data = { id: Number(options.id) }
    if (options['dry-run']) {
      print(await agentPreview('packlist.confirm', data, { resourceId: options.id, asnCode: options['asn-code'] || '' }), json)
    } else {
      print(await request('/asn/serial/packlists/confirm/', {
        method: 'POST',
        headers: agentConfirmationHeaders(options, 'packlist confirm'),
        json: data
      }), json)
    }
    return
  }

  const receivingActions = {
    create: { operation: 'receiving.create', endpoint: '/receiving/records/' },
    'staging-assign': { operation: 'receiving.staging_assign', endpoint: '/receiving/staging/assign/' },
    qc: { operation: 'receiving.qc_complete', endpoint: '/receiving/qc/complete/' },
    resolve: { operation: 'receiving.resolve_exception', endpoint: '/receiving/exceptions/resolve/' },
    putaway: { operation: 'receiving.putaway', endpoint: '/receiving/putaway/' },
    reconcile: { operation: 'receiving.reconcile', endpoint: '/receiving/reconcile/' },
    'resolve-reconciliation': { operation: 'receiving.resolve_reconciliation', endpoint: '/receiving/reconcile/resolve/' }
  }
  if (resource === 'receiving' && receivingActions[action]) {
    const definition = receivingActions[action]
    const data = action === 'create'
      ? validateReceivingCreateData(parseData(options))
      : parseData(options)
    await runProtectedJsonCommand({
      operation: definition.operation,
      endpoint: definition.endpoint,
      data,
      options,
      json,
    })
    return
  }
  if (resource === 'receiving' && action === 'exceptions') {
    print(await request('/receiving/exceptions/'), json)
    return
  }

  const transportActions = {
    create: { operation: 'transport.create', endpoint: '/transport/orders/' },
    assign: { operation: 'transport.assign', endpoint: '/transport/assign/' },
    transition: { operation: 'transport.transition', endpoint: '/transport/transition/' }
  }
  if (resource === 'transport' && transportActions[action]) {
    const definition = transportActions[action]
    await runProtectedJsonCommand({
      operation: definition.operation,
      endpoint: definition.endpoint,
      data: parseData(options),
      options,
      json,
    })
    return
  }

  throw new Error(`Unknown command: ${operation}`)
}

main().catch(error => {
  const message = error.message
  const operation = process.argv.slice(2).filter(value => !value.startsWith('--')).join(' ')
  process.stderr.write(`Error: ${message}\nNext action: ${recoveryHint(message, operation)}\n`)
  process.exitCode = 1
})
