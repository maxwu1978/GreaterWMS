#!/usr/bin/env node

import { readFileSync, statSync } from 'node:fs'
import { basename, resolve } from 'node:path'

const DEFAULT_URL = 'https://greaterwms-v2-test3-sn.onrender.com'

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
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload)
    throw new Error(`HTTP ${response.status}: ${detail}`)
  }
  return payload
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

function print (payload, json) {
  process.stdout.write(json ? `${JSON.stringify(payload, null, 2)}\n` : `${payload.detail || 'success'}\n${JSON.stringify(payload, null, 2)}\n`)
}

function help () {
  process.stdout.write(`GreaterWMS Pack List CLI\n\nUsage:\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist list --asn-code ASN [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist import --asn-code ASN --file FILE --dry-run [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist import --asn-code ASN --file FILE --confirm [--json]\n  GREATERWMS_TOKEN=... node tools/greaterwms.mjs packlist confirm --id ID --confirm [--json]\n\nEnvironment:\n  GREATERWMS_URL       GreaterWMS base URL (default: ${DEFAULT_URL})\n  GREATERWMS_TOKEN     authenticated openid token from the current GreaterWMS session\n  GREATERWMS_OPERATOR  optional staff id used for the audit operator\n  GREATERWMS_LANGUAGE  optional response language (default: en-US)\n\nImport is two-step: run --dry-run, review the returned rows and quantities, then run --confirm.\n`)
}

async function main () {
  const { options, positional } = parseArgs(process.argv.slice(2))
  const [resource, action] = positional
  const json = Boolean(options.json)
  if (options.help || resource !== 'packlist' || !action) {
    help()
    return
  }

  if (action === 'list') {
    if (!options['asn-code']) throw new Error('--asn-code is required')
    const query = `?asn_code=${encodeURIComponent(options['asn-code'])}`
    print(await request(`/asn/serial/packlists/${query}`), json)
    return
  }

  if (action === 'import') {
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

  if (action === 'confirm') {
    if (!options.id) throw new Error('--id is required')
    if (!options.confirm) throw new Error('Confirmation is a write operation. Repeat with --confirm.')
    print(await request('/asn/serial/packlists/confirm/', { method: 'POST', json: { id: Number(options.id) } }), json)
    return
  }

  throw new Error(`Unknown packlist action: ${action}`)
}

main().catch(error => {
  process.stderr.write(`Error: ${error.message}\n`)
  process.exitCode = 1
})
