#!/usr/bin/env node
/*
 * GreaterWMS 生产仿真 —— Node 运行器(供 Codex 在终端执行,免浏览器)
 * 自包含:内嵌浏览器版工具箱 + 注册/登录 + 命令行入口。需 Node ≥ 18。
 *
 * 用法:
 *   首次(注册 SIM 租户 + 冒烟 D0):
 *     node wms-sim-node.mjs --register --user SIM-TENANT-01 --pass '<强密码>' --day 0
 *   后续各日(同一租户,不带 --register):
 *     node wms-sim-node.mjs --user SIM-TENANT-01 --pass '<强密码>' --day 1
 *     node wms-sim-node.mjs --user SIM-TENANT-01 --pass '<强密码>' --day 2
 *     node wms-sim-node.mjs --user SIM-TENANT-01 --pass '<强密码>' --day 3
 *   必填:--api <URL>；SIM 账号必须以 SIM- 开头。
 *   生产环境还必须显式传入 --confirm-production-sim。
 *   仅准备隔离租户(不创建业务数据):
 *     node wms-sim-node.mjs --register-only --api <URL> --user SIM-TENANT-01 --pass '<强密码>' --confirm-production-sim
 *   可选:--days 0,1(一进程连跑)| --cleanup --confirm-cleanup
 * 每次运行结束会在当前目录写出 sim-results-*.json —— 发给 Claude 分析。
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : d; };
const has = k => argv.includes('--' + k);
const API = arg('api');
const USER = arg('user'); const PASS = arg('pass');
const INSPECTION_FILE = arg('inspection-file', '');
const CONFIRM_PRODUCTION = has('confirm-production-sim');
const CONFIRM_CLEANUP = has('confirm-cleanup');
const REGISTER_ONLY = has('register-only');
let API_HOST = '';
try { API_HOST = API ? new URL(API).hostname.toLowerCase() : ''; } catch { API_HOST = ''; }
const IS_PRODUCTION = /(^|\.)maxsmartwms\.online$/i.test(API_HOST);
if (!API || !USER || !PASS || !/^SIM[-_]/i.test(USER) || (!REGISTER_ONLY && !has('register') && !argv.some(value => value === '--day' || value === '--days')) || (IS_PRODUCTION && !CONFIRM_PRODUCTION) || (has('cleanup') && !CONFIRM_CLEANUP)) {
  console.log('用法: node wms-sim-node.mjs --api <URL> --user <SIM账号> --pass <密码> [--register | --register-only] [--day 0 | --days 0,1] [--inspection-file <xlsx>] [--cleanup --confirm-cleanup] [--confirm-production-sim]');
  if (IS_PRODUCTION && !CONFIRM_PRODUCTION) console.error('拒绝执行:生产 API 必须显式传入 --confirm-production-sim');
  if (has('cleanup') && !CONFIRM_CLEANUP) console.error('拒绝执行:清理必须显式传入 --confirm-cleanup');
  if (USER && !/^SIM[-_]/i.test(USER)) console.error('拒绝执行:仿真账号必须以 SIM- 或 SIM_ 开头');
  process.exit(1);
}
// ---- 浏览器环境垫片 ----
const LS = new Map();
globalThis.window = globalThis;
globalThis.localStorage = { getItem: k => (LS.has(k) ? LS.get(k) : null), setItem: (k, v) => LS.set(k, String(v)) };
globalThis.document = { createElement: () => ({ click() {}, set href(_) {}, set download(_) {} }) };
if (typeof globalThis.Blob === 'undefined') globalThis.Blob = class { constructor() {} };
if (!globalThis.URL.createObjectURL) globalThis.URL.createObjectURL = () => '';
// ---- 注册(可选)+ 登录 ----
async function _post(path, body) {
  const r = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  let j; try { j = await r.json(); } catch { j = {}; }
  return [r.status, j];
}
if (has('register') || REGISTER_ONLY) {
  const [rs, rj] = await _post('/register/', { name: USER, password1: PASS, password2: PASS });
  const tok = rj && rj.data && (rj.data.openid || rj.data.token);
  console.log('[register]', rs, tok ? 'ok(新 SIM 租户已创建)' : JSON.stringify(rj).slice(0, 200) + '(若提示已存在则直接登录)');
}
const [_ls, _lj] = await _post('/login/', { name: USER, password: PASS });
const L = (_lj && _lj.data) || {};
const TOKEN = String(L.token || L.openid || '');
if (!TOKEN.startsWith('gwms_')) { console.error('[login] 失败', _ls, JSON.stringify(_lj).slice(0, 240)); process.exit(1); }
localStorage.setItem('openid', TOKEN);
localStorage.setItem('login_id', L.user_id);
console.log(`[login] ok user_id=${L.user_id} staff_type=${L.staff_type} tenant=${String(L.tenant_openid || '').slice(0, 6)}…`);
if (REGISTER_ONLY) {
  console.log('[register-only] 隔离 SIM 租户已准备完成，未创建业务数据');
  process.exit(0);
}
// ================= 以下为内嵌的浏览器版工具箱(与 wms-sim-toolkit.js 同源) =================
/*
 * GreaterWMS 生产仿真工具箱 v1 —— 30~50柜/天 全流程模拟
 * 适配部署版本 bae94284(所有端点/字段按源码核对)
 *
 * 用法:
 *   1) 在 app.maxsmartwms.online 用管理员登录(强烈建议独立 SIM 租户,见测试方案)
 *   2) F12 → Console → 粘贴本文件全部内容回车
 *   3) 依次执行:
 *        await SIM.seed()        // 主数据 + 8角色员工 + 3司机 + 12 SKU + 辅助字典
 *        await SIM.runDay(0)     // D0 冒烟(10柜,每场景1个)
 *        await SIM.roles()       // 角色看板指示核验
 *        await SIM.verify()      // 库存/暂存位/SN 不变量对账
 *        SIM.report()            // 汇总
 *        SIM.export()            // 下载 JSON 结果(发回给 Claude 分析)
 *        await SIM.runDay(1) / runDay(2) / runDay(3)   // 常规40 / 异常30 / 峰值50
 *        await SIM.cleanup()     // 删除可删的 SIM 数据(收货单/SN/库存行无删除接口,详见方案)
 *
 * 说明:pack list / pick ticket 走 AI-agent 通道(X-AGENT-CLIENT + 预览→确认两阶段),
 *       其余按人工操作;NEG 场景"被拒绝"= 通过。所有对象带 SIM 前缀。
 */
window.SIM = (() => {
  'use strict';
  const CFG = {
    api: '',
    TAG: 'SIM',
    delay: 140,                 // 每次 API 调用间隔 ms(限流)
    timeout: 30000,
    maxRetries: 3,
    inspectionFile: INSPECTION_FILE,
    agentRatio: 0.7,            // pack list / pick ticket 走 AI-agent 的比例
    dayPlans: {                 // 每日柜量与异常权重
      0: { containers: 10, smoke: true },
      1: { containers: 40, excRate: 0.10 },
      2: { containers: 30, excRate: 0.40 },
      3: { containers: 50, excRate: 0.08 },
    },
  };
  const strip = v => String(v == null ? '' : v).replace(/^__q_(strn|numb|bool)\|/, '');
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const pad = (n, w) => String(n).padStart(w, '0');
  const S = {
    run: 'R' + Math.random().toString(36).slice(2, 6).toUpperCase(),
    seq: 0, admin: {}, staff: {}, drivers: [], skus: [], bins: [],
    ledger: { containers: [], roleChecks: [], verify: [], notes: [], stockExp: {}, closedRefs: [], openRefs: [], serials: { shipped: [], returned: [] } },
    created: [],
    base: {}, seeded: false,
  };
  const nid = p => `${CFG.TAG}-${S.run}-${p}${pad(++S.seq, 3)}`;
  const sim = suffix => `${CFG.TAG}-${S.run}-${suffix}`;
  const rnd = (a, b) => a + Math.floor(Math.random() * (b - a + 1));
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const rememberCreated = (path, row) => {
    if (row && row.id != null && !S.created.some(item => item.path === path && String(item.id) === String(row.id))) {
      S.created.push({ path, id: row.id });
    }
    return row;
  };

  // ---------- HTTP ----------
  async function api(path, { method = 'GET', body, form, token, operator, agent, headers, _attempt = 0 } = {}) {
    const h = Object.assign({ 'Content-Type': 'application/json' }, headers || {});
    if (form) { delete h['Content-Type']; delete h['content-type']; }
    if (operator != null && !token) return [0, { detail: 'missing role token', code: 'SIM_ROLE_TOKEN_MISSING' }];
    h.token = token || S.admin.token;
    if (!h.token) return [0, { detail: 'missing authentication token', code: 'SIM_TOKEN_MISSING' }];
    h.operator = String(operator != null ? operator : (S.admin.id || '1'));
    if (agent) h['X-AGENT-CLIENT'] = 'greaterwms-cli';
    await sleep(CFG.delay);
    let r, t;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CFG.timeout);
    try {
      r = await fetch(CFG.api + path, { method, headers: h, cache: 'no-store', body: form || (body ? JSON.stringify(body) : undefined), signal: controller.signal });
      t = await r.text();
    } catch (e) {
      if (_attempt < CFG.maxRetries && (method === 'GET' || method === 'HEAD' || body?.idempotency_key)) {
        await sleep(400 * (2 ** _attempt) + rnd(0, 250));
        return api(path, { method, body, form, token, operator, agent, headers, _attempt: _attempt + 1 });
      }
      return [0, { detail: 'network:' + e.message, code: 'SIM_NETWORK_ERROR' }];
    } finally { clearTimeout(timer); }
    let j; try { j = JSON.parse(t); } catch (e) { j = { __raw: (t || '').slice(0, 160) }; }
    const retryableStatus = r.status === 429 || [502, 503, 504].includes(r.status);
    if (retryableStatus && _attempt < CFG.maxRetries && (method === 'GET' || method === 'HEAD' || body?.idempotency_key)) {
      await sleep(400 * (2 ** _attempt) + rnd(0, 250));
      return api(path, { method, body, form, token, operator, agent, headers, _attempt: _attempt + 1 });
    }
    return [r.status, j];
  }
  // AI-agent 两阶段:预览拿 confirmation_token → 原 payload + token + idempotency_key 确认执行
  async function agentExec(path, payload, operation, { resourceId = '', asnCode = '', token, operator, method = 'POST' } = {}) {
    const t = token, op = operator;
    if (!t || !op) return [0, { detail: 'agent operator token is missing', code: 'SIM_AGENT_IDENTITY_MISSING' }, { phase: 'identity' }];
    const [ps, pj] = await api('/asn/serial/agent/preview/', {
      method: 'POST', token: t, operator: op, agent: true,
      body: { operation, payload, resource_id: String(resourceId || ''), asn_code: asnCode || '' },
    });
    if (ps !== 200 || !pj.confirmation_token) return [ps, pj, { phase: 'preview' }];
    const body = Object.assign({}, payload, { confirmation_token: pj.confirmation_token, idempotency_key: 'IK-' + nid('K') });
    const [es, ej] = await api(path, { method, token: t, operator: op, agent: true, body });
    return [es, ej, { phase: 'exec', preview_id: pj.preview_id, token: pj.confirmation_token, sent: body }];
  }
  async function inspectionImport(asnCode, filePath, { token, operator } = {}) {
    if (!filePath) return [204, { detail: 'inspection file not provided', skipped: true }];
    const bytes = fs.readFileSync(filePath);
    const makeForm = controls => {
      const form = new FormData();
      form.append('file', new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), 'inspection.xlsx');
      form.append('asn_code', asnCode);
      form.append('mode', 'receive');
      form.append('allow_all', 'true');
      form.append('source_type', 'AI_AGENT');
      form.append('note', 'SIM QC inspection import');
      for (const [key, value] of Object.entries(controls || {})) form.append(key, String(value));
      return form;
    };
    const [ps, preview] = await api('/asn/serial/inspections/preview/', {
      method: 'POST', token, operator, agent: true, form: makeForm(),
    });
    const command = preview && preview.agent;
    if (ps < 200 || ps >= 300 || !command?.confirmation_token) return [ps, preview, { phase: 'inspection-preview' }];
    return api('/asn/serial/inspections/import/', {
      method: 'POST', token, operator, agent: true,
      form: makeForm({ confirmation_token: command.confirmation_token, idempotency_key: 'IK-' + nid('QC') }),
    }).then(([status, body]) => [status, body, { phase: 'inspection-import', preview_id: command.preview_id }]);
  }

  // ---------- 台账 ----------
  const exp = g => (S.ledger.stockExp[g] = S.ledger.stockExp[g] || { recv: 0, ship: 0, ret: 0 });
  const C = (type) => { const c = { id: nid('C'), type, steps: [], ok: true, refs: {} }; S.ledger.containers.push(c); return c; };
  function step(c, name, st, j, expectation = null) {
    const okHttp = st >= 200 && st < 300;
    const expectFail = expectation === true || Boolean(expectation && (expectation.rejected || expectation.status));
    const expectedStatuses = expectation && Array.isArray(expectation.status) ? expectation.status : null;
    const actualDetail = JSON.stringify(j && (j.detail || j)).slice(0, 240);
    const expectedStatusOk = !expectedStatuses || expectedStatuses.includes(st);
    const forbiddenDetail = expectation && expectation.notDetail && actualDetail.toLowerCase().includes(String(expectation.notDetail).toLowerCase());
    const ok = expectFail
      ? !okHttp && expectedStatusOk && !forbiddenDetail
      : okHttp;
    c.steps.push({ name, http: st, ok, expectFail, msg: ok ? '' : actualDetail });
    if (!ok) c.ok = false;
    return okHttp ? j : null;
  }

  // ---------- 主数据 ----------
  async function ensure(path, listQ, existsFn, body, opt) {
    const [, l] = await api(path + (listQ || '?max_page=200'), opt || {});
    const rows = (l && (l.results || l)) || [];
    const hit = Array.isArray(rows) ? rows.find(existsFn) : null;
    if (hit) return hit;
    const [st, j] = await api(path, Object.assign({ method: 'POST', body }, opt || {}));
    if (st >= 300) S.ledger.notes.push(`seed:${path} -> ${st} ${JSON.stringify(j).slice(0, 120)}`);
    const [, l2] = await api(path + (listQ || '?max_page=200'), opt || {});
    const created = ((l2 && (l2.results || l2)) || []).find(existsFn) || null;
    if (st >= 200 && st < 300) rememberCreated(path, created);
    return created;
  }
  async function seed() {
    const tk = strip(localStorage.getItem('openid')), oid = strip(localStorage.getItem('login_id'));
    if (!tk.startsWith('gwms_')) { console.log('%c❌ 请先用 ADMIN LOGIN 登录再运行', 'color:#c00;font-weight:bold'); return; }
    if (!oid) throw new Error('管理员 operator id 缺失');
    S.admin = { token: tk, id: oid };
    console.log('%c[SIM] seeding… run=' + S.run, 'color:#08c');
    // 员工(应用内 PIN 工号)+ 令牌
    const roles = { MGR: 'Manager', WH: 'Warehouse', QC: 'QC', IB: 'Inbound', OB: 'Outbound', LG: 'Logistics', SC: 'StockControl', T1: 'Driver', T2: 'Driver' };
    const names = { T1: sim('Tom'), T2: sim('David') };
    for (const k of Object.keys(roles)) {
      const name = names[k] || sim(k);
      const pin = 300000 + (Array.from(name).reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) % 99991, 7) + 9); // 按姓名确定性生成,重复运行可复用
      const [, existing] = await api(`/staff/?staff_name=${encodeURIComponent(name)}`);
      let created = false;
      let row = ((existing && existing.results) || []).find(x => x.staff_name === name) || null;
      if (!row) {
        const [ss] = await api('/staff/', { method: 'POST', body: { staff_name: name, staff_type: roles[k], check_code: pin, creater: 'sim' } });
        created = ss >= 200 && ss < 300;
      }
      const [, lg] = await api(`/staff/?staff_name=${encodeURIComponent(name)}&check_code=${pin}`);
      const [, li] = await api(`/staff/?staff_name=${encodeURIComponent(name)}`);
      row = ((li && li.results) || []).find(x => x.staff_name === name) || {};
      if (created) rememberCreated('/staff/', row);
      if (!row.id || String(row.staff_type || '').toLowerCase() !== roles[k].toLowerCase()) {
        throw new Error(`SIM staff ${name} 不存在或角色不匹配`);
      }
      S.staff[k] = { name, role: roles[k], id: row.id, pin, token: lg && lg.auth_token };
      if (!S.staff[k].token) throw new Error(`SIM staff ${name} 未拿到独立令牌`);
    }
    // 司机(与 Driver 员工同名 → 司机角色按姓名收窄)
    for (const d of [sim('Tom'), sim('David'), sim('Leo')]) {
      await ensure('/driver/', `?driver_name=${encodeURIComponent(d)}`, x => x.driver_name === d,
        { driver_name: d, license_plate: 'SIM-' + d.slice(-3).toUpperCase(), contact: '000', creater: 'sim' });
      S.drivers.push(d);
    }
    // 客户/供应商
    for (const s of [sim('SUP-A'), sim('SUP-B')]) await ensure('/supplier/', `?supplier_name=${s}`, x => x.supplier_name === s,
      { supplier_name: s, supplier_city: 'SZ', supplier_address: 'SIM', supplier_contact: 100, supplier_manager: 'SIM', supplier_level: 1, creater: 'sim' });
    for (const c of [sim('CUST-A'), sim('CUST-B')]) await ensure('/customer/', `?customer_name=${c}`, x => x.customer_name === c,
      { customer_name: c, customer_city: 'SZ', customer_address: 'SIM', customer_contact: 100, customer_manager: 'SIM', customer_level: 1, creater: 'sim' });
    // 商品辅助字典(租户内必须存在)
    const aux = [['/goodsunit/', 'goods_unit', 'EA'], ['/goodsclass/', 'goods_class', 'SIMC'], ['/goodsbrand/', 'goods_brand', 'SIMB'],
      ['/goodscolor/', 'goods_color', 'NA'], ['/goodsshape/', 'goods_shape', 'NA'], ['/goodsspecs/', 'goods_specs', 'NA'], ['/goodsorigin/', 'goods_origin', 'CN']];
    for (const [p, f, v] of aux) await ensure(p, '', x => x[f] === v, { [f]: v, creater: 'sim' });
    // 12 个 SKU:R*(Receiving 流) L*(legacy ASN) N*(SN 管理)
    const defs = [];
    for (let i = 1; i <= 6; i++) defs.push([sim('R' + pad(i, 2)), sim('SUP-A')]);
    for (let i = 1; i <= 2; i++) defs.push([sim('L' + pad(i, 2)), sim('SUP-B')]);
    for (let i = 1; i <= 4; i++) defs.push([sim('N' + pad(i, 2)), sim('SUP-B')]);
    for (const [g, sup] of defs) {
      await ensure('/goods/', `?goods_code=${g}`, x => x.goods_code === g, {
        goods_code: g, goods_desc: g + ' desc', goods_supplier: sup, goods_weight: 500, goods_w: 10, goods_d: 10, goods_h: 10,
        goods_unit: 'EA', goods_class: 'SIMC', goods_brand: 'SIMB', goods_color: 'NA', goods_shape: 'NA', goods_specs: 'NA',
        goods_origin: 'CN', goods_cost: 10, goods_price: 15, creater: 'sim' });
      S.skus.push(g);
    }
    // 仿真专用库存库位:禁止写入租户已有库位
    const simBinSize = `${CFG.TAG}-${S.run}-STD`;
    await ensure('/binsize/', `?bin_size=${encodeURIComponent(simBinSize)}`, x => x.bin_size === simBinSize,
      { bin_size: simBinSize, bin_size_w: 100, bin_size_d: 100, bin_size_h: 100, creater: 'sim' });
    const bins = [];
    for (let i = 1; i <= 6; i++) {
      const binName = `${CFG.TAG}-${S.run}-B${pad(i, 2)}`;
      const row = await ensure('/binset/', `?bin_name=${encodeURIComponent(binName)}`, x => x.bin_name === binName,
        { bin_name: binName, bin_size: simBinSize, bin_property: 'Normal', empty_label: true, creater: 'sim' });
      if (!row) throw new Error(`SIM storage bin ${binName} 创建失败`);
      bins.push(binName);
    }
    S.bins = bins;
    // 库存基线快照:verify() 用"基线+本次台账增量"对账,支持同一租户多次运行
    for (const g of S.skus) {
      const [, sl0] = await api(`/stock/list/?goods_code=${g}`);
      const r0 = ((sl0 && sl0.results) || []).find(x => x.goods_code === g) || {};
      S.base[g] = {
        goods_qty: Number(r0.goods_qty || 0),
        onhand: Number(r0.onhand_stock || 0),
        can_order: Number(r0.can_order_stock || 0),
        asn_stock: Number(r0.asn_stock || 0),
      };
    }
    const [, slots] = await api('/staging/slots/?flow=INBOUND');
    S.ledger.notes.push(`staging slots(INBOUND)=${(slots || []).length ?? 'n/a'}`);
    S.seeded = true;
    console.log('%c[SIM] seed 完成:staff=%o drivers=%o skus=%d bins=%d', 'color:#0a0', Object.fromEntries(Object.entries(S.staff).map(([k, v]) => [k, v.token ? 'ok' : 'NO-TOKEN'])), S.drivers, S.skus.length, S.bins.length);
  }

  // ---------- 通用小步骤 ----------
  const freeSlots = async (flow, count = 1) => {
    const [status, s] = await api('/staging/slots/?flow=' + flow);
    const rows = Array.isArray(s) ? s : [];
    const free = rows.filter(x => x.available === true && !x.reserved && !x.occupied);
    if (free.length < count) {
      S.ledger.notes.push(`没有足够可用${flow}暂存位(status=${status}, free=${free.length}, need=${count})`);
      return [];
    }
    return free.slice(0, count).map(x => x.bin_name || x.name);
  };
  const freeSlot = async flow => (await freeSlots(flow, 1))[0] || null;
  const listId = async (path, key, code) => { const [, l] = await api(`${path}?${key}=${encodeURIComponent(code)}`); const r = ((l && l.results) || []).find(x => x[key] === code); return r && r.id; };
  async function boardCheck(roleKey, ref, { present = true, nextAction, etaStatus, note } = {}) {
    const st = S.staff[roleKey]; if (!st || !st.token) return;
    const [, b] = await api('/dashboard/operations/?view=active&limit=500', { token: st.token, operator: st.id });
    const items = (b && b.items) || [];
    const hit = items.find(i => String(i.reference) === String(ref));
    let ok = present ? !!hit : !hit;
    let detail = hit ? `next=${hit.next_action || hit.operation} assigned_to=${hit.assigned_to}` : 'absent';
    if (ok && present && nextAction && hit && String(hit.next_action || hit.operation) !== nextAction) { ok = false; detail += ` (期望 ${nextAction})`; }
    if (ok && present && etaStatus && hit && String(hit.eta_status || '') !== etaStatus) { ok = false; detail += ` (ETA 期望 ${etaStatus})`; }
    S.ledger.roleChecks.push({ role: roleKey + '/' + (st.role || ''), ref, expect: present ? ('可见' + (nextAction ? ':' + nextAction : '') + (etaStatus ? ` ETA:${etaStatus}` : '')) : '不可见', ok, detail, note: note || '' });
  }

  // ---------- 进仓场景 ----------
  async function inboundReceiving(kind) { // clean|short|over|damage
    const c = C('IN-recv-' + kind);
    const goods = pick(S.skus.filter(s => s.includes('-R'))), qty = rnd(40, 160);
    const plan = { clean: [qty, qty, 0], short: [qty, qty - rnd(5, 15), 0], over: [qty, qty + rnd(5, 15), 0], damage: [qty, qty, rnd(2, 6)] }[kind];
    const [expQ, actQ, dmg] = plan, rc = nid('RC');
    const stgIn = await freeSlot('INBOUND'); // 新版必须绑定实际暂存位
    let j = step(c, 'create-receipt', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, customer: sim('SUP-A'), staging_bins: stgIn ? [stgIn] : [], details: [{ goods_code: goods, expected_qty: expQ, actual_qty: actQ, damage_qty: dmg }] } })));
    if (!j) return c;
    c.refs.receipt = rc;
    rememberCreated('/receiving/records/', { id: await listId('/receiving/records/', 'receipt_no', rc) });
    await boardCheck('QC', rc, { present: true, note: 'QC 应看到待检' });
    j = step(c, 'qc', ...(await api('/receiving/qc/complete/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: { receipt_no: rc, details: [{ goods_code: goods, actual_qty: actQ, damage_qty: dmg, exception_note: (kind !== 'clean' ? 'SIM ' + kind : '') }] } })));
    if (!j) return c;
    if (kind === 'damage') {
      const finalStatus = String(j.status || '').toUpperCase();
      if (finalStatus !== 'QC_EXCEPTION') {
        c.ok = false;
        c.steps.push({ name: 'damage-open-exception-state', http: 200, ok: false, msg: `unexpected status ${finalStatus}` });
      } else {
        S.ledger.openRefs.push(rc);
      }
      return c;
    }
    if ((j.status || '') === 'QC_EXCEPTION') {
      const resolved = step(c, 'resolve-exception', ...(await api('/receiving/exceptions/resolve/', {
        method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id,
        body: { receipt_no: rc, action: 'ACCEPT_FOR_PUTAWAY', note: 'SIM resolve ' + kind, details: [{ goods_code: goods }] },
      })));
      if (!resolved) return c;
    }
    const drv = pick([sim('Tom'), sim('David')]);
    if (!step(c, 'assign-putaway-driver', ...(await api('/receiving/putaway/assign/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, driver_name: drv } })))) return c;
    const drvK = drv === sim('Tom') ? 'T1' : 'T2';
    await boardCheck(drvK, rc, { present: true, note: '被派司机应看到上架任务' });
    await boardCheck(drvK === 'T1' ? 'T2' : 'T1', rc, { present: false, note: '另一司机不应看到' });
    const put = actQ - dmg;
    j = step(c, 'putaway(driver)', ...(await api('/receiving/putaway/', { method: 'POST', token: S.staff[drvK].token, operator: S.staff[drvK].id, body: { receipt_no: rc, goods_code: goods, quantity: put, bin_name: pick(S.bins), driver_name: drv, idempotency_key: rc + '-P1' } })));
    if (j) {
      exp(goods).recv += put;
      const finalStatus = String(j.status || '').toUpperCase();
      const closed = ['PUTAWAY_COMPLETE', 'CLOSED'].includes(finalStatus);
      if (!closed) { c.ok = false; c.steps.push({ name: 'receiving-terminal-state', http: 200, ok: false, msg: `unexpected status ${finalStatus}` }); }
      else S.ledger.closedRefs.push(rc);
    }
    return c;
  }
  async function inboundAsnSN({ agent = true } = {}) { // AI-agent 导入 pack list 的 SN 柜
    const c = C('IN-asn-SN' + (agent ? '-agent' : ''));
    const goods = pick(S.skus.filter(s => s.includes('-N'))), qty = rnd(8, 20);
    let j = step(c, 'asn-create', ...(await api('/asn/list/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { creater: 'sim' } })));
    if (!j) return c;
    const asn = j.asn_code || (j.detail && j.detail.asn_code) || j.data?.asn_code; c.refs.asn = asn;
    if (!asn) { step(c, 'asn-code-missing', 500, j); return c; }
    j = step(c, 'asn-detail', ...(await api('/asn/detail/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { asn_code: asn, supplier: sim('SUP-B'), goods_code: [goods], goods_qty: [qty] } })));
    if (!j) return c;
    const sns = Array.from({ length: qty }, (_, i) => `${asn}-SN${pad(i + 1, 3)}`);
    const rows = sns.map(sn => ({ goods_code: goods, serial_number: sn, goods_qty: 1 }));
    if (agent) { // pack list 经 AI-agent 通道
      let [st, pj] = await api('/asn/serial/packlists/create/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, agent: true, body: { asn_code: asn, rows, source_type: 'AI_AGENT', package_qty: qty } });
      if (st >= 400 && JSON.stringify(pj).includes('AGENT_CONFIRMATION_REQUIRED')) [st, pj] = await agentExec('/asn/serial/packlists/create/', { asn_code: asn, rows, source_type: 'AI_AGENT', package_qty: qty }, 'packlist.import', { asnCode: asn });
      step(c, 'packlist-import(agent)', st, pj);
      const docId = pj && pj.document && pj.document.id;
      if (docId) {
        const [cs, cj, meta] = await agentExec('/asn/serial/packlists/confirm/', { id: docId }, 'packlist.confirm', {
          resourceId: docId,
          asnCode: asn,
          token: S.staff.IB.token,
          operator: S.staff.IB.id,
        });
        step(c, 'packlist-confirm(agent两阶段)', cs, cj);
        if (cs === 200 && meta && meta.token) { // NEG-7:同令牌重放应返回缓存(幂等),篡改 payload 应拒
          const [rs, rj] = await api('/asn/serial/packlists/confirm/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, agent: true, body: Object.assign({}, meta.sent) });
          step(c, 'agent-replay-idempotent', rs, rj);
          const [ts, tj] = await api('/asn/serial/packlists/confirm/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, agent: true, body: Object.assign({}, meta.sent, { id: docId, note: 'tamper' }) });
          step(c, 'agent-tamper-rejected', ts, tj, { rejected: true, status: [400, 409, 422] });
        }
      }
    } else {
      step(c, 'packlist-import(manual)', ...(await api('/asn/serial/packlists/create/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { asn_code: asn, rows, source_type: 'MANUAL' } })));
    }
    const aid = await listId('/asn/list/', 'asn_code', asn);
    rememberCreated('/asn/list/', { id: aid });
    const eta = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    const etaResult = await agentExec(`/asn/eta/${aid}/`, { expected_arrival_at: eta, source: 'SIM-CUSTOMER' }, 'asn.eta', {
      resourceId: aid, asnCode: asn, token: S.staff.IB.token, operator: S.staff.IB.id,
    });
    const etaBody = step(c, 'eta-update(agent)', ...etaResult);
    if (etaBody && !(etaBody.asn || etaBody.expected_arrival_at)) {
      c.ok = false;
      c.steps.push({ name: 'eta-response', http: 200, ok: false, msg: 'ETA is missing from response' });
    }
    await boardCheck('IB', asn, { present: true, etaStatus: 'ON_TIME', note: 'ETA 已提供且应在看板显示' });
    step(c, 'arrival', ...(await api(`/asn/arrival/${aid}/`, { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: {} })));
    const slots = await freeSlots('INBOUND', qty);
    if (slots.length === qty) {
      step(c, 'reserve-staging', ...(await api(`/asn/reserve-staging/${aid}/`, {
        method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id,
        body: { staging_bins: slots },
      })));
    } else {
      step(c, 'reserve-staging', 409, { detail: `need ${qty} inbound staging slots` });
      return c;
    }
    await boardCheck('WH', asn, { present: true, note: '到货后仓库应见指派卸货指示' });
    const drv = sim('Leo');
    if (!step(c, 'unload-start', ...(await api(`/asn/preload/${aid}/`, {
      method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id,
      body: { unload_driver: drv, staging_bins: slots },
    })))) return c;
    for (const sn of sns) { const [ss, sj] = await api('/asn/serial/scan/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: { asn_code: asn, goods_code: goods, serial_number: sn } }); if (ss >= 300) { step(c, 'scan-' + sn, ss, sj); break; } }
    c.steps.push({ name: `scan×${qty}`, http: 200, ok: true, msg: '' });
    if (CFG.inspectionFile) {
      step(c, 'qc-inspection-import(agent)', ...(await inspectionImport(asn, CFG.inspectionFile, { token: S.staff.IB.token, operator: S.staff.IB.id })));
    }
    step(c, 'presort', ...(await api(`/asn/presort/${aid}/`, { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: {} })));
    step(c, 'sorted', ...(await api('/asn/sorted/', { method: 'PUT', token: S.staff.WH.token, operator: S.staff.WH.id, body: { asn_code: asn, supplier: sim('SUP-B'), goodsData: [{ goods_code: goods, goods_actual_qty: qty }] } })));
    const did = await listId('/asn/detail/', 'asn_code', asn);
    rememberCreated('/asn/detail/', { id: did });
    const putawayPayload = { asn_code: asn, goods_code: goods, qty, bin_name: pick(S.bins), putaway_driver: drv };
    // Legacy ASN+SN putaway is an Inbound workflow command. Warehouse operators
    // use the controlled Receiving putaway endpoint above instead.
    const putawayResult = await agentExec(`/asn/movetobin/${did}/`, putawayPayload, 'asn.putaway', {
      resourceId: did,
      asnCode: asn,
      token: S.staff.IB.token,
      operator: S.staff.IB.id,
    });
    const j2 = step(c, 'putaway(movetobin-agent)', ...putawayResult);
    if (j2) {
      exp(goods).recv += qty; c.refs.sns = sns; c.refs.goods = goods;
      const finalStatus = String(j2.status || '').toUpperCase();
      if (['5', 'COMPLETED', 'CLOSED', 'PUTAWAY_COMPLETE'].includes(finalStatus) || Number(j2.asn_status) === 5 || j2.detail === 'success' || j2.Detail === 'success') S.ledger.closedRefs.push(asn);
      else c.ok = false;
    }
    return c;
  }
  async function negMixing() { // NEG-1 互斥;验证后释放测试占用的暂存位
    const c = C('NEG-mixing'); const goods = pick(S.skus.filter(s => s.includes('-L')));
    let j = step(c, 'asn-create', ...(await api('/asn/list/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { creater: 'sim' } })));
    if (!j) return c; const asn = j.asn_code; c.refs.asn = asn;
    j = step(c, 'asn-detail', ...(await api('/asn/detail/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { asn_code: asn, supplier: sim('SUP-B'), goods_code: [goods], goods_qty: [10] } })));
    if (j) exp(goods).asnOpen = (exp(goods).asnOpen || 0) + 10;
    await boardCheck('IB', asn, { present: true, etaStatus: 'NOT_PROVIDED', note: '未提供 ETA 应明确显示' });
    const claimSlot = await freeSlot('INBOUND');
    const claimRef = nid('RC');
    step(c, 'receiving-claim', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: claimRef, customer: sim('SUP-B'), linked_asn_code: asn, staging_bins: claimSlot ? [claimSlot] : [], details: [{ goods_code: goods, actual_qty: 10 }] } })));
    c.refs.receipt = claimRef;
    const secondClaimSlot = await freeSlot('INBOUND');
    step(c, 'second-claim-rejected', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: nid('RC'), customer: sim('SUP-B'), linked_asn_code: asn, staging_bins: secondClaimSlot ? [secondClaimSlot] : [], details: [{ goods_code: goods, actual_qty: 10 }] } })), { rejected: true, status: [400, 409, 422], notDetail: 'staging' });
    const [releaseStatus, releaseBody] = await api('/staging/release/', {
      method: 'POST',
      token: S.staff.WH.token,
      operator: S.staff.WH.id,
      body: { flow: 'INBOUND', reference_code: claimRef },
    });
    step(c, 'release-test-staging', releaseStatus, releaseBody);
    if (releaseStatus >= 200 && releaseStatus < 300) S.ledger.closedRefs.push(claimRef);
    return c;
  }

  // ---------- 出仓场景 ----------
  async function outboundCommon(c, { goods, qty, sn = false, serials = [], agent = false }) {
    const tokOB = { token: S.staff.OB.token, operator: S.staff.OB.id };
    const createPayload = {
      creater: 'sim',
      customer: sim('CUST-A'),
      picking_mode: sn ? 'SN' : 'SKU_QTY',
      transport_required: true,
      ship_to: 'SIM-DESTINATION',
    };
    let createResult = agent
      ? await agentExec('/dn/list/', createPayload, 'outbound.create', tokOB)
      : await api('/dn/list/', Object.assign({ method: 'POST', body: createPayload }, tokOB));
    let j = step(c, 'dn-create' + (agent ? '(agent)' : ''), ...createResult);
    if (!j) return null; const dn = j.dn_code; c.refs.dn = dn;
    const detailBody = { dn_code: dn, customer: sim('CUST-A'), goods_code: [goods], goods_qty: [qty] };
    if (sn) detailBody.serial_numbers = [serials];
    const detailResult = agent
      ? await agentExec('/dn/detail/', detailBody, 'outbound.detail.create', Object.assign({ resourceId: dn }, tokOB))
      : await api('/dn/detail/', Object.assign({ method: 'POST', body: detailBody }, tokOB));
    j = step(c, sn ? 'dn-detail(pick ticket' + (agent ? '·agent' : '') + ')' : 'dn-detail', ...detailResult);
    if (!j) return null;
    const id = await listId('/dn/list/', 'dn_code', dn);
    rememberCreated('/dn/list/', { id });
    if (!id) { step(c, 'dn-id-missing', 500, { detail: 'DN id missing' }); return null; }
    if (!step(c, 'neworder', ...(await api(`/dn/neworder/${id}/`, Object.assign({ method: 'POST', body: {} }, tokOB))))) return null;
    const releasePath = `/dn/orderrelease/?dn_code=${encodeURIComponent(dn)}`;
    const releaseResult = agent
      ? await agentExec(releasePath, {}, 'outbound.order_release', Object.assign({ resourceId: id }, tokOB))
      : await api(releasePath, Object.assign({ method: 'POST', body: {} }, tokOB));
    if (!step(c, 'orderrelease' + (agent ? '(agent)' : ''), ...releaseResult)) return null;
    const [, pl] = await api(`/dn/pickinglist/${id}/`, tokOB);
    const rows = (pl && (pl.results || pl)) || [];
    const goodsData = (Array.isArray(rows) ? rows : []).filter(r => r.t_code).map(r => { const g = { t_code: r.t_code, goods_code: r.goods_code, pick_qty: r.pick_qty }; if (sn) g.serial_numbers = serials; return g; });
    if (!goodsData.length) { step(c, 'pickinglist-empty', 500, pl); return null; }
    const pickPayload = { dn_code: dn, customer: sim('CUST-A'), goodsData };
    const pickPath = `/dn/picked/${id}/`;
    const pickResult = agent
      ? await agentExec(pickPath, pickPayload, 'outbound.pick', Object.assign({ resourceId: id, method: 'POST' }, tokOB))
      : await api(pickPath, Object.assign({ method: 'POST', body: pickPayload }, tokOB));
    if (!step(c, 'picked' + (agent ? '(agent)' : ''), ...pickResult)) return null;
    return { dn, id };
  }
  async function outboundFlow(kind, { agent = false } = {}) { // clean|sn|podexc|cancelreturn
    const sn = kind === 'sn';
    const c = C('OUT-' + kind + (agent && sn ? '-agent' : ''));
    let goods, qty, serials = [];
    if (sn) { const src = S.ledger.containers.find(x => x.type.startsWith('IN-asn-SN') && x.ok && x.refs.sns && x.refs.sns.length >= 3 && !x.refs.used); if (!src) { c.steps.push({ name: 'no-sn-stock', http: 0, ok: true, msg: '跳过(无可用SN库存)' }); return c; } goods = src.refs.goods; serials = src.refs.sns.slice(0, rnd(2, Math.min(5, src.refs.sns.length))); qty = serials.length; src.refs.used = true; }
    else { goods = pick(S.skus.filter(s => s.includes('-R'))); const have = exp(goods).recv - exp(goods).ship; if (have < 5) { c.steps.push({ name: 'no-stock', http: 0, ok: true, msg: '跳过(库存不足)' }); return c; } qty = rnd(3, Math.min(40, have)); }
    const r = await outboundCommon(c, { goods, qty, sn, serials, agent });
    if (!r) return c;
    const drv = pick([sim('Tom'), sim('David')]), drvK = drv === sim('Tom') ? 'T1' : 'T2';
    const slot = await freeSlot('OUTBOUND');
    const dispatchPayload = { dn_code: r.dn, driver: drv, staging_bin: slot };
    const dispatchResult = agent
      ? await agentExec(`/dn/dispatch/${r.id}/`, dispatchPayload, 'outbound.dispatch', { resourceId: r.id, token: S.staff.OB.token, operator: S.staff.OB.id })
      : await api(`/dn/dispatch/${r.id}/`, { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: dispatchPayload });
    const j = step(c, 'dispatch' + (agent ? '(agent)' : ''), ...dispatchResult);
    if (!j) return c;
    exp(goods).ship += qty;
    await boardCheck(drvK, 'TR-' + r.dn, { present: true, note: '司机应看到自己的运输任务' }).catch(() => {});
    const tno = 'TR-' + r.dn;
    const [, transportRows] = await api(`/transport/orders/?transport_no=${encodeURIComponent(tno)}`, { token: S.staff[drvK].token, operator: S.staff[drvK].id });
    const transport = (transportRows && (transportRows.results || transportRows))?.[0];
    if (String(transport?.status || '').toUpperCase() === 'IN_TRANSIT') {
      c.steps.push({ name: 'driver-depart(IN_TRANSIT)', http: 200, ok: true, msg: 'already in transit after dispatch' });
    } else {
      step(c, 'driver-depart(IN_TRANSIT)', ...(await api('/transport/transition/', { method: 'POST', token: S.staff[drvK].token, operator: S.staff[drvK].id, body: { transport_no: tno, status: 'IN_TRANSIT' } })));
    }
    if (kind === 'cancelreturn') {
      step(c, 'cancel-intransit(admin)', ...(await api(`/dn/cancel-intransit/${r.id}/`, { method: 'POST', body: { cancellation_note: 'SIM 取消在途,货物退回' } })));
      const rc = nid('RC');
      const stgRet = await freeSlot('INBOUND'); // 退货收货同样需绑定暂存位
      const returnReceipt = step(c, 'return-receipt', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, customer: sim('CUST-A'), source_type: 'OUTBOUND_RETURN', source_reference: r.dn, staging_bins: stgRet ? [stgRet] : [], details: [{ goods_code: goods, actual_qty: qty }] } })));
      if (returnReceipt) rememberCreated('/receiving/records/', { id: await listId('/receiving/records/', 'receipt_no', rc) });
      const qcBody = { receipt_no: rc, details: [{ goods_code: goods, actual_qty: qty }] };
      if (sn) qcBody.details[0].serials = serials;
      step(c, 'return-qc', ...(await api('/receiving/qc/complete/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: qcBody })));
      step(c, 'return-assign', ...(await api('/receiving/putaway/assign/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, driver_name: sim('Leo') } })));
      const pj = step(c, 'return-putaway', ...(await api('/receiving/putaway/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, goods_code: goods, quantity: qty, bin_name: pick(S.bins), driver_name: sim('Leo'), idempotency_key: rc + '-P1' } })));
      if (pj) exp(goods).ret += qty;
      const secondReturnSlot = await freeSlot('INBOUND');
      step(c, 'NEG-double-return-rejected', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: nid('RC'), customer: sim('CUST-A'), source_type: 'OUTBOUND_RETURN', source_reference: r.dn, staging_bins: secondReturnSlot ? [secondReturnSlot] : [], details: [{ goods_code: goods, actual_qty: qty }] } })), { rejected: true, status: [400, 409, 422], notDetail: 'staging' });
      if (pj) S.ledger.closedRefs.push(rc);
      if (sn) S.ledger.serials.returned.push(...serials.map(s => ({ sn: s, goods })));
      S.ledger.closedRefs.push(r.dn);
      return c;
    }
    step(c, 'driver-arrive(ARRIVED)', ...(await api('/transport/transition/', { method: 'POST', token: S.staff[drvK].token, operator: S.staff[drvK].id, body: { transport_no: tno, status: 'ARRIVED' } })));
    let pod;
    if (kind === 'podexc') {
      const short = Math.max(1, Math.floor(qty * 0.1)), dmg = qty > 3 ? 1 : 0;
      step(c, 'pod-missing-note-rejected', ...(await api(`/dn/pod/${r.id}/`, { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: { dn_code: r.dn, goodsData: [{ goods_code: goods, intransit_qty: qty - short, delivery_damage_qty: dmg }] } })), { rejected: true, status: [400, 409, 422] });
      pod = { dn_code: r.dn, goodsData: [{ goods_code: goods, intransit_qty: qty - short, delivery_damage_qty: dmg, delivery_note: 'SIM 短交' + short + ' 破损' + dmg }] };
    } else pod = { dn_code: r.dn, goodsData: [{ goods_code: goods, intransit_qty: qty, delivery_damage_qty: 0 }] };
    step(c, 'pod', ...(await api(`/dn/pod/${r.id}/`, { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: pod })));
    const [, completedRows] = await api(`/transport/orders/?transport_no=${encodeURIComponent(tno)}`, { token: S.staff.LG.token, operator: S.staff.LG.id });
    const completedTransport = (completedRows && (completedRows.results || completedRows))?.[0];
    step(c, 'transport-auto-completed',
      completedTransport && String(completedTransport.status || '').toUpperCase() === 'COMPLETED' ? 200 : 500,
      { status: completedTransport && completedTransport.status });
    if (sn) S.ledger.serials.shipped.push(...serials.map(s => ({ sn: s, goods })));
    S.ledger.closedRefs.push(r.dn);
    return c;
  }
  async function negReship() { // NEG-2 已发运 SN 再分配
    const c = C('NEG-sn-reship');
    const s = S.ledger.serials.shipped[0];
    if (!s) { c.steps.push({ name: 'skip(no shipped sn)', http: 0, ok: true, msg: '' }); return c; }
    const j = step(c, 'dn-create', ...(await api('/dn/list/', { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: { creater: 'sim', picking_mode: 'SN' } })));
    if (!j) return c;
    step(c, 'reallocate-shipped-sn-rejected', ...(await api('/dn/detail/', { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: { dn_code: j.dn_code, customer: sim('CUST-A'), goods_code: [s.goods], goods_qty: [1], serial_numbers: [[s.sn]] } })), { rejected: true, status: [400, 409, 422] });
    return c;
  }
  async function negAuthz() { // NEG-8 越权抽查
    const c = C('NEG-authz');
    step(c, 'QC写财务被拒', ...(await api('/capital/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: { capital_name: sim('CAPITAL'), capital_qty: 1, capital_cost: 1, creater: 'x' } })), { rejected: true, status: [400, 401, 403, 409, 422] });
    step(c, '司机建员工被拒', ...(await api('/staff/', { method: 'POST', token: S.staff.T1.token, operator: S.staff.T1.id, body: { staff_name: sim('ESC'), staff_type: 'Manager', check_code: 111111, creater: 'x' } })), { rejected: true, status: [400, 401, 403, 409, 422] });
    c.steps.push({ name: '司机B流转司机A任务被拒', http: 0, ok: true, skipped: true, msg: '未执行:需要独立的跨司机任务夹具' });
    S.ledger.notes.push('authz:跨司机任务冒用仍需专用夹具覆盖');
    return c;
  }

  // ---------- 日运行 ----------
  async function runDay(n = 0, opts = {}) {
    if (!S.seeded) { console.log('先 await SIM.seed()'); return; }
    const plan = Object.assign({}, CFG.dayPlans[n] || CFG.dayPlans[1], opts);
    console.log(`%c[SIM] Day${n} 开始:${plan.containers} 柜`, 'color:#08c;font-weight:bold');
    const jobs = [];
    if (plan.smoke) {
      jobs.push(() => inboundReceiving('clean'), () => inboundReceiving('short'), () => inboundReceiving('damage'),
        () => inboundAsnSN({ agent: true }), () => negMixing(), () => outboundFlow('clean'),
        () => outboundFlow('sn', { agent: true }), () => outboundFlow('podexc'), () => outboundFlow('cancelreturn'), () => negAuthz());
    } else {
      const inN = Math.round(plan.containers * 0.55), outN = plan.containers - inN, ex = plan.excRate || 0.1;
      for (let i = 0; i < inN; i++) {
        const r = Math.random();
        if (r < CFG.agentRatio * 0.5) jobs.push(() => inboundAsnSN({ agent: true }));
        else if (r < CFG.agentRatio * 0.5 + ex) jobs.push(() => inboundReceiving(pick(['short', 'over', 'damage'])));
        else jobs.push(() => inboundReceiving('clean'));
      }
      for (let i = 0; i < outN; i++) {
        const r = Math.random();
        if (r < 0.3) jobs.push(() => outboundFlow('sn', { agent: Math.random() < CFG.agentRatio }));
        else if (r < 0.3 + ex) jobs.push(() => outboundFlow(pick(['podexc', 'cancelreturn'])));
        else jobs.push(() => outboundFlow('clean'));
      }
      jobs.push(() => negReship(), () => negAuthz());
    }
    let done = 0;
    for (const job of jobs) { try { await job(); } catch (e) { S.ledger.notes.push('day' + n + ' 异常:' + e.message); } done++; if (done % 5 === 0) console.log(`[SIM] Day${n}: ${done}/${jobs.length}`); }
    console.log(`%c[SIM] Day${n} 完成`, 'color:#0a0;font-weight:bold'); report();
  }

  // ---------- 角色看板核验 ----------
  async function rolesAudit() {
    console.log('%c[SIM] 角色看板核验', 'color:#08c');
    for (const k of Object.keys(S.staff)) {
      const st = S.staff[k]; if (!st.token) continue;
      for (const view of ['active', 'history']) {
        const [hs, b] = await api(`/dashboard/operations/?view=${view}&limit=500`, { token: st.token, operator: st.id });
        const items = (b && b.items) || [];
        const role = String(st.role || '').toLowerCase();
        const inScope = item => {
          const category = String(item.category || '').toLowerCase();
          const assigned = String(item.assigned_role || '').toUpperCase();
          if (['manager', 'supervisor'].includes(role)) return true;
          if (role === 'driver') {
            if (view === 'active') return assigned === 'DRIVER' && String(item.assignee_name || '').toLowerCase() === st.name.toLowerCase();
            return (item.history_roles || []).includes('DRIVER') && (item.history_assignees || []).some(name => String(name).toLowerCase() === st.name.toLowerCase());
          }
          if (view === 'history') {
            if (role === 'qc') return (item.history_roles || []).includes('QC');
            if (role === 'warehouse') return (item.history_roles || []).includes('WAREHOUSE');
            if (role === 'logistics') return (item.history_roles || []).includes('LOGISTICS');
            if (role === 'stockcontrol') return (item.history_roles || []).includes('WAREHOUSE');
            if (role === 'inbound') return ['inbound', 'receiving'].includes(category);
            if (role === 'outbound') return category === 'outbound';
          }
          if (role === 'qc') return assigned === 'QC';
          if (role === 'warehouse') return assigned === 'WAREHOUSE';
          if (role === 'logistics') return assigned === 'LOGISTICS' || category === 'transport';
          if (role === 'stockcontrol') return ['WAREHOUSE', 'QC'].includes(assigned);
          if (role === 'inbound') return ['inbound', 'receiving'].includes(category);
          if (role === 'outbound') return category === 'outbound';
          return false;
        };
        const bad = items.filter(item => !inScope(item));
        const missingNext = view === 'active' ? items.filter(item => !String(item.next_action || item.operation || '').trim()) : [];
        const badHistory = view === 'history' ? items.filter(item => !['completed', 'cancelled'].includes(String(item.lane || '').toLowerCase())) : [];
        const ok = hs === 200 && bad.length === 0 && missingNext.length === 0 && badHistory.length === 0;
        S.ledger.roleChecks.push({ role: k + '/' + st.role, ref: `${view} 全景`, expect: '严格角色范围+下一步', ok,
          detail: `count=${items.length}${bad.length ? ' 越界:' + bad.slice(0, 3).map(i => i.reference) : ''}${missingNext.length ? ` missing_next=${missingNext.length}` : ''}${badHistory.length ? ` active_in_history=${badHistory.length}` : ''}` });
      }
    }
    console.table(S.ledger.roleChecks.slice(-20));
    return S.ledger.roleChecks.filter(item => !item.ok).length === 0;
  }

  // ---------- 不变量对账 ----------
  async function verify() {
    console.log('%c[SIM] 对账/不变量', 'color:#08c');
    S.ledger.verify = [];
    for (const g of S.skus) {
      const e = S.ledger.stockExp[g]; if (!e) continue;
      const [, sl] = await api(`/stock/list/?goods_code=${g}`);
      const row = ((sl && sl.results) || []).find(x => x.goods_code === g) || {};
      const b = S.base[g] || { goods_qty: 0, onhand: 0, can_order: 0, asn_stock: 0 };
      const want = e.recv - e.ship + e.ret;
      // GreaterWMS goods_qty includes open ASN reservations; onhand_stock is
      // the physical quantity already received and put away.
      const openAsn = Number(e.asnOpen || 0);
      const checks = [
        ['goods_qty', Number(row.goods_qty || 0), b.goods_qty + want + openAsn],
        ['onhand', Number(row.onhand_stock || 0), b.onhand + want],
        ['can_order', Number(row.can_order_stock || 0), b.can_order + want],
        ['asn_stock', Number(row.asn_stock || 0), Number(b.asn_stock || 0) + Number(e.asnOpen || 0)],
        ['dn_stock=0', Number(row.dn_stock || 0), 0],
      ];
      for (const [nm, got, exp2] of checks) S.ledger.verify.push({ sku: g, check: nm, got, want: exp2, ok: got === exp2 });
    }
    const [, asg] = await api('/staging/assignments/?max_page=500');
    const assignments = Array.isArray(asg) ? asg : ((asg && asg.results) || []);
    const live = new Set(['ACTIVE', 'RESERVED']);
    const closedLeaks = assignments.filter(a => live.has(String(a.status || '').toUpperCase()) && S.ledger.closedRefs.includes(String(a.reference_code)));
    const missingOpen = S.ledger.openRefs.filter(ref => !assignments.some(a => String(a.reference_code) === String(ref) && live.has(String(a.status || '').toUpperCase())));
    S.ledger.verify.push({ sku: '(staging)', check: '闭环单据无残留占用', got: closedLeaks.length, want: 0, ok: closedLeaks.length === 0 });
    S.ledger.verify.push({ sku: '(staging)', check: '开放异常保持可追踪占用', got: missingOpen.length, want: 0, ok: missingOpen.length === 0 });
    const currentRefs = new Set([...S.ledger.closedRefs, ...S.ledger.openRefs].map(String));
    const unclassified = assignments.filter(a => String(a.reference_code || '').startsWith(`${CFG.TAG}-${S.run}-`) && !currentRefs.has(String(a.reference_code)));
    S.ledger.verify.push({ sku: '(staging)', check: '本次运行暂存任务均有预期状态', got: unclassified.length, want: 0, ok: unclassified.length === 0 });
    const fails = S.ledger.verify.filter(v => !v.ok);
    console.table(fails.length ? fails : S.ledger.verify.slice(0, 12));
    console.log(fails.length ? `%c❌ ${fails.length} 项不变量未过` : '%c✅ 不变量全绿', fails.length ? 'color:#c00;font-weight:bold' : 'color:#0a0;font-weight:bold');
    return fails.length === 0;
  }

  // ---------- 汇总/导出/清理 ----------
  function report() {
    const cs = S.ledger.containers;
    const byType = {};
    cs.forEach(c => { byType[c.type] = byType[c.type] || { n: 0, ok: 0 }; byType[c.type].n++; if (c.ok) byType[c.type].ok++; });
    console.log('%c===== SIM 汇总 =====', 'color:#08c;font-weight:bold');
    console.table(Object.entries(byType).map(([t, v]) => ({ 场景: t, 数量: v.n, 通过: v.ok, 失败: v.n - v.ok })));
    const fails = cs.filter(c => !c.ok).map(c => ({ id: c.id, type: c.type, step: (c.steps.find(s => !s.ok) || {}).name, http: (c.steps.find(s => !s.ok) || {}).http, msg: (c.steps.find(s => !s.ok) || {}).msg }));
    if (fails.length) { console.log('%c失败明细:', 'color:#c00'); console.table(fails); } else console.log('%c✅ 全部柜通过', 'color:#0a0;font-weight:bold');
    const rc = S.ledger.roleChecks.filter(r => !r.ok);
    if (rc.length) { console.log('%c角色核验未过:', 'color:#c00'); console.table(rc); }
    if (S.ledger.notes.length) console.log('notes:', S.ledger.notes);
    return { scenarioFailures: fails.length, roleFailures: rc.length };
  }
  function exportState() {
    const blob = new Blob([JSON.stringify({ run: S.run, when: new Date().toISOString(), cfg: CFG, ledger: S.ledger, staff: Object.fromEntries(Object.entries(S.staff).map(([k, v]) => [k, { name: v.name, role: v.role, id: v.id }])) }, null, 2)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `sim-results-${S.run}.json`; a.click();
    console.log('已导出 sim-results-' + S.run + '.json —— 请发给 Claude 分析');
  }
  async function cleanup() {
    console.log('%c[SIM] 清理本次 run 的资源…', 'color:#08c');
    const failures = [];
    const remove = async (path, id) => {
      if (id == null) return;
      const [status, body] = await api(`${path}${id}/`, { method: 'DELETE' });
      if (![200, 204].includes(status)) failures.push(`${path}${id}: HTTP ${status} ${JSON.stringify(body).slice(0, 120)}`);
    };
    // 只删除本次 rememberCreated 记录，禁止按 SIM 前缀扫描删除其他运行的数据。
    for (const item of [...S.created].reverse()) await remove(item.path, item.id);
    const [, assignmentsBody] = await api('/staging/assignments/?max_page=500');
    const assignments = Array.isArray(assignmentsBody) ? assignmentsBody : ((assignmentsBody && assignmentsBody.results) || []);
    const live = assignments.filter(item => ['ACTIVE', 'RESERVED'].includes(String(item.status || '').toUpperCase()) &&
      [...S.ledger.closedRefs, ...S.ledger.openRefs].includes(String(item.reference_code)));
    if (live.length) failures.push(`暂存位仍有在用分配: ${live.map(item => item.reference_code + '@' + item.bin_name).join(', ')}`);
    const undeletable = S.ledger.containers.filter(c => c.refs.asn || c.refs.receipt || c.refs.dn);
    if (undeletable.length) failures.push(`工作流记录可能仍有不可删除审计数据: ${undeletable.length} 条; 需使用独立 SIM 租户重置`);
    S.ledger.notes.push(`cleanup created=${S.created.length} failures=${failures.length}`);
    if (failures.length) {
      S.ledger.notes.push(...failures);
      throw new Error('清理未完成: ' + failures.join('; '));
    }
    console.log('%c[SIM] 本次可删除资源清理完成', 'color:#0a0');
    return true;
  }
  const help = () => console.log(`SIM 命令:
  await SIM.seed()        建主数据+角色+司机+SKU
  await SIM.runDay(0)     冒烟10柜 | runDay(1) 40柜 | runDay(2) 异常30柜 | runDay(3) 峰值50柜
  --inspection-file <xlsx>  在 ASN+SN 场景通过 AI-agent 导入 QC 验收文件
  await SIM.roles()       各角色看板指示核验(active+history)
  await SIM.verify()      库存守恒/暂存位/不变量对账
  SIM.report()            汇总表   SIM.export() 导出JSON发给Claude
  await SIM.cleanup()     删除可删的SIM数据`);
  help();
  return { seed, runDay, roles: rolesAudit, verify, report, export: exportState, cleanup, help, _state: S, _cfg: CFG };
})();
// ================= CLI 执行序列 =================
SIM._cfg.api = API;
const daysArg = arg('days', arg('day', '0'));
let fatal = null;
let roleOk = false;
let verifyOk = false;
try {
  await SIM.seed();
  if (!SIM._state.seeded) throw new Error('seed 未完成');
  const dayValues = String(daysArg).split(',').map(s => s.trim()).filter(Boolean).map(Number);
  if (!dayValues.length || dayValues.some(value => !Number.isInteger(value) || value < 0 || value > 3)) {
    throw new Error('day 必须是 0 到 3 的整数列表');
  }
  for (const day of dayValues) await SIM.runDay(day);
  roleOk = await SIM.roles();
  verifyOk = await SIM.verify();
} catch (error) {
  fatal = error;
  console.error('[SIM] 执行失败:', error && error.stack ? error.stack : error);
}
let cleanupOk = has('cleanup') ? false : null;
if (has('cleanup') && SIM._state.seeded) {
  try { cleanupOk = await SIM.cleanup(); } catch (error) {
    cleanupOk = false;
    console.error('[SIM] 清理失败:', error && error.stack ? error.stack : error);
  }
}
const summary = SIM.report();
const OUT = `sim-results-${SIM._state.run}.json`;
fs.writeFileSync(OUT, JSON.stringify({
  run: SIM._state.run,
  when: new Date().toISOString(),
  api: API, user: USER, days: daysArg,
  ledger: SIM._state.ledger,
  base: SIM._state.base,
  created: SIM._state.created,
  result: { fatal: fatal ? String(fatal.message || fatal) : '', roleOk, verifyOk, cleanupOk, summary },
  staff: Object.fromEntries(Object.entries(SIM._state.staff).map(([k, v]) => [k, { name: v.name, role: v.role, id: v.id, token: v.token ? 'ok' : 'MISSING' }])),
}, null, 2));
const failed = Boolean(fatal) || !roleOk || !verifyOk || (has('cleanup') && !cleanupOk) || (summary && (summary.scenarioFailures || summary.roleFailures));
if (failed) {
  process.exitCode = 1;
  console.error('\n❌ 仿真未通过，结果已写入 ' + OUT);
} else {
  console.log('\n✅ 结果已写入 ' + OUT + ' —— 请把此文件发给 Claude 分析');
}
