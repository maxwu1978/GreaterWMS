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
    api: 'https://api.maxsmartwms.online',
    TAG: 'SIM',
    delay: 140,                 // 每次 API 调用间隔 ms(限流)
    timeoutMs: 30000,
    maxRetries: 3,
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
    ledger: { containers: [], roleChecks: [], verify: [], notes: [], stockExp: {}, closedRefs: [], serials: { shipped: [], returned: [] } },
    base: {}, seeded: false,
  };
  const nid = p => `${CFG.TAG}-${S.run}-${p}${pad(++S.seq, 3)}`;
  const rnd = (a, b) => a + Math.floor(Math.random() * (b - a + 1));
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];

  // ---------- HTTP ----------
  async function api(path, { method = 'GET', body, token, operator, agent, headers, retry = 0 } = {}) {
    const h = Object.assign({ 'Content-Type': 'application/json' }, headers || {});
    h.token = token || S.admin.token;
    h.operator = String(operator != null ? operator : (S.admin.id || '1'));
    if (agent) h['X-AGENT-CLIENT'] = 'greaterwms-cli';
    await sleep(CFG.delay);
    let r, t;
    try {
      r = await fetch(CFG.api + path, {
        method,
        headers: h,
        cache: 'no-store',
        body: body ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(CFG.timeoutMs),
      });
      t = await r.text();
    } catch (e) {
      if (retry < CFG.maxRetries) {
        await sleep(Math.min(5000, 500 * (2 ** retry)));
        return api(path, { method, body, token, operator, agent, headers, retry: retry + 1 });
      }
      return [0, { detail: 'network:' + e.message, retry_limit: CFG.maxRetries }];
    }
    let j; try { j = JSON.parse(t); } catch (e) { j = { __raw: (t || '').slice(0, 160) }; }
    if (r.status === 429 || r.status >= 500) {
      if (retry < CFG.maxRetries) {
        const retryAfter = Number(r.headers.get('retry-after'));
        const delay = Number.isFinite(retryAfter) && retryAfter > 0
          ? Math.min(5000, retryAfter * 1000)
          : Math.min(5000, 500 * (2 ** retry));
        await sleep(delay);
        return api(path, { method, body, token, operator, agent, headers, retry: retry + 1 });
      }
      j.retry_limit = CFG.maxRetries;
    }
    return [r.status, j];
  }
  // AI-agent 两阶段:预览拿 confirmation_token → 原 payload + token + idempotency_key 确认执行
  async function agentExec(path, payload, operation, { resourceId = '', asnCode = '', token, operator, method = 'POST' } = {}) {
    const t = token || S.staff.IB?.token, op = operator || S.staff.IB?.id;
    const [ps, pj] = await api('/asn/serial/agent/preview/', {
      method: 'POST', token: t, operator: op, agent: true,
      body: { operation, payload, resource_id: String(resourceId || ''), asn_code: asnCode || '' },
    });
    if (ps !== 200 || !pj.confirmation_token) return [ps, pj, { phase: 'preview' }];
    const body = Object.assign({}, payload, { confirmation_token: pj.confirmation_token, idempotency_key: 'IK-' + nid('K') });
    const [es, ej] = await api(path, { method, token: t, operator: op, agent: true, body });
    return [es, ej, { phase: 'exec', preview_id: pj.preview_id, token: pj.confirmation_token, sent: body }];
  }

  // ---------- 台账 ----------
  const exp = g => (S.ledger.stockExp[g] = S.ledger.stockExp[g] || { recv: 0, ship: 0, ret: 0 });
  const C = (type) => { const c = { id: nid('C'), type, steps: [], ok: true, refs: {} }; S.ledger.containers.push(c); return c; };
  function step(c, name, st, j, expectFail) {
    const okHttp = st >= 200 && st < 300;
    const ok = expectFail ? !okHttp : okHttp;
    c.steps.push({ name, http: st, ok, expectFail: !!expectFail, msg: ok ? '' : JSON.stringify(j && (j.detail || j)).slice(0, 200) });
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
    return ((l2 && (l2.results || l2)) || []).find(existsFn) || null;
  }
  async function seed() {
    const tk = strip(localStorage.getItem('openid')), oid = strip(localStorage.getItem('login_id')) || '1';
    if (!tk.startsWith('gwms_')) { console.log('%c❌ 请先用 ADMIN LOGIN 登录再运行', 'color:#c00;font-weight:bold'); return; }
    S.admin = { token: tk, id: oid };
    console.log('%c[SIM] seeding… run=' + S.run, 'color:#08c');
    // 员工(应用内 PIN 工号)+ 令牌
    const roles = { MGR: 'Manager', WH: 'Warehouse', QC: 'QC', IB: 'Inbound', OB: 'Outbound', LG: 'Logistics', SC: 'StockControl', T1: 'Driver', T2: 'Driver' };
    const names = { T1: 'SIM-Tom', T2: 'SIM-David' };
    for (const k of Object.keys(roles)) {
      const name = names[k] || `${CFG.TAG}_${k}`;
      const pin = 300000 + (Array.from(name).reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) % 99991, 7) + 9); // 按姓名确定性生成,重复运行可复用
      await api('/staff/', { method: 'POST', body: { staff_name: name, staff_type: roles[k], check_code: pin, creater: 'sim' } });
      const [, lg] = await api(`/staff/?staff_name=${encodeURIComponent(name)}&check_code=${pin}`);
      const [, li] = await api(`/staff/?staff_name=${encodeURIComponent(name)}`);
      const row = ((li && li.results) || []).find(x => x.staff_name === name) || {};
      S.staff[k] = { name, role: roles[k], id: row.id, pin, token: lg && lg.auth_token };
      if (!S.staff[k].token) S.ledger.notes.push(`seed:staff ${name} 未拿到令牌`);
    }
    // 司机(与 Driver 员工同名 → 司机角色按姓名收窄)
    for (const d of ['SIM-Tom', 'SIM-David', 'SIM-Leo']) {
      await ensure('/driver/', `?driver_name=${encodeURIComponent(d)}`, x => x.driver_name === d,
        { driver_name: d, license_plate: 'SIM-' + d.slice(-3).toUpperCase(), contact: '000', creater: 'sim' });
      S.drivers.push(d);
    }
    // 客户/供应商
    for (const s of ['SIM-SUP-A', 'SIM-SUP-B']) await ensure('/supplier/', `?supplier_name=${s}`, x => x.supplier_name === s,
      { supplier_name: s, supplier_city: 'SZ', supplier_address: 'SIM', supplier_contact: 100, supplier_manager: 'SIM', supplier_level: 1, creater: 'sim' });
    for (const c of ['SIM-CUST-A', 'SIM-CUST-B']) await ensure('/customer/', `?customer_name=${c}`, x => x.customer_name === c,
      { customer_name: c, customer_city: 'SZ', customer_address: 'SIM', customer_contact: 100, customer_manager: 'SIM', customer_level: 1, creater: 'sim' });
    // 商品辅助字典(租户内必须存在)
    const aux = [['/goodsunit/', 'goods_unit', 'EA'], ['/goodsclass/', 'goods_class', 'SIMC'], ['/goodsbrand/', 'goods_brand', 'SIMB'],
      ['/goodscolor/', 'goods_color', 'NA'], ['/goodsshape/', 'goods_shape', 'NA'], ['/goodsspecs/', 'goods_specs', 'NA'], ['/goodsorigin/', 'goods_origin', 'CN']];
    for (const [p, f, v] of aux) await ensure(p, '', x => x[f] === v, { [f]: v, creater: 'sim' });
    // 12 个 SKU:R*(Receiving 流) L*(legacy ASN) N*(SN 管理)
    const defs = [];
    for (let i = 1; i <= 6; i++) defs.push(['SIM-R' + pad(i, 2), 'SIM-SUP-A']);
    for (let i = 1; i <= 2; i++) defs.push(['SIM-L' + pad(i, 2), 'SIM-SUP-B']);
    for (let i = 1; i <= 4; i++) defs.push(['SIM-N' + pad(i, 2), 'SIM-SUP-B']);
    for (const [g, sup] of defs) {
      await ensure('/goods/', `?goods_code=${g}`, x => x.goods_code === g, {
        goods_code: g, goods_desc: g + ' desc', goods_supplier: sup, goods_weight: 500, goods_w: 10, goods_d: 10, goods_h: 10,
        goods_unit: 'EA', goods_class: 'SIMC', goods_brand: 'SIMB', goods_color: 'NA', goods_shape: 'NA', goods_specs: 'NA',
        goods_origin: 'CN', goods_cost: 10, goods_price: 15, creater: 'sim' });
      S.skus.push(g);
    }
    // 库位:优先复用既有 Normal 库位,不足则建 SIM 库位
    let [, bl] = await api('/binset/?max_page=500');
    let bins = ((bl && bl.results) || []).filter(b => b.bin_property === 'Normal').map(b => b.bin_name);
    if (bins.length < 4) {
      await ensure('/binsize/', '?bin_size=SIM-STD', x => x.bin_size === 'SIM-STD', { bin_size: 'SIM-STD', bin_size_w: 100, bin_size_d: 100, bin_size_h: 100, creater: 'sim' });
      for (let i = 1; i <= 6; i++) await ensure('/binset/', `?bin_name=SIM-B${pad(i, 2)}`, x => x.bin_name === 'SIM-B' + pad(i, 2),
        { bin_name: 'SIM-B' + pad(i, 2), bin_size: 'SIM-STD', bin_property: 'Normal', empty_label: true, creater: 'sim' });
      [, bl] = await api('/binset/?max_page=500');
      bins = ((bl && bl.results) || []).filter(b => b.bin_property === 'Normal').map(b => b.bin_name);
    }
    S.bins = bins;
    // 库存基线快照:verify() 用"基线+本次台账增量"对账,支持同一租户多次运行
    for (const g of S.skus) {
      const [, sl0] = await api(`/stock/list/?goods_code=${g}`);
      const r0 = ((sl0 && sl0.results) || []).find(x => x.goods_code === g) || {};
      S.base[g] = { goods_qty: Number(r0.goods_qty || 0), onhand: Number(r0.onhand_stock || 0), can_order: Number(r0.can_order_stock || 0), asn_stock: Number(r0.asn_stock || 0) };
    }
    const [, slots] = await api('/staging/slots/?flow=INBOUND');
    S.ledger.notes.push(`staging slots(INBOUND)=${(slots || []).length ?? 'n/a'}`);
    S.seeded = true;
    console.log('%c[SIM] seed 完成:staff=%o drivers=%o skus=%d bins=%d', 'color:#0a0', Object.fromEntries(Object.entries(S.staff).map(([k, v]) => [k, v.token ? 'ok' : 'NO-TOKEN'])), S.drivers, S.skus.length, S.bins.length);
  }

  // ---------- 通用小步骤 ----------
  const freeSlot = async flow => { const [, s] = await api('/staging/slots/?flow=' + flow); const f = (Array.isArray(s) ? s : []).find(x => (x.status || '').toUpperCase() !== 'ACTIVE' && !x.occupied) || (Array.isArray(s) ? s[0] : null); return f && (f.bin_name || f.name); };
  const listId = async (path, key, code) => { const [, l] = await api(`${path}?${key}=${encodeURIComponent(code)}`); const r = ((l && l.results) || []).find(x => x[key] === code); return r && r.id; };
  async function boardCheck(roleKey, ref, { present = true, nextAction, note } = {}) {
    const st = S.staff[roleKey]; if (!st || !st.token) return;
    const [, b] = await api('/dashboard/operations/?view=active&limit=500', { token: st.token, operator: st.id });
    const items = (b && b.items) || [];
    const hit = items.find(i => String(i.reference) === String(ref));
    let ok = present ? !!hit : !hit;
    let detail = hit ? `next=${hit.next_action || hit.operation} assigned_to=${hit.assigned_to}` : 'absent';
    if (ok && present && nextAction && hit && String(hit.next_action || hit.operation) !== nextAction) { ok = false; detail += ` (期望 ${nextAction})`; }
    S.ledger.roleChecks.push({ role: roleKey + '/' + (st.role || ''), ref, expect: present ? ('可见' + (nextAction ? ':' + nextAction : '')) : '不可见', ok, detail, note: note || '' });
  }

  // ---------- 进仓场景 ----------
  async function inboundReceiving(kind) { // clean|short|over|damage
    const c = C('IN-recv-' + kind);
    const goods = pick(S.skus.filter(s => s.includes('-R'))), qty = rnd(40, 160);
    const plan = { clean: [qty, qty, 0], short: [qty, qty - rnd(5, 15), 0], over: [qty, qty + rnd(5, 15), 0], damage: [qty, qty, rnd(2, 6)] }[kind];
    const [expQ, actQ, dmg] = plan, rc = nid('RC');
    const stgIn = await freeSlot('INBOUND'); // 新版必须绑定实际暂存位
    let j = step(c, 'create-receipt', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, customer: 'SIM-SUP-A', staging_bins: stgIn ? [stgIn] : [], details: [{ goods_code: goods, expected_qty: expQ, actual_qty: actQ, damage_qty: dmg }] } })));
    if (!j) return c;
    c.refs.receipt = rc;
    await boardCheck('QC', rc, { present: true, note: 'QC 应看到待检' });
    j = step(c, 'qc', ...(await api('/receiving/qc/complete/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: { receipt_no: rc, details: [{ goods_code: goods, actual_qty: actQ, damage_qty: dmg, exception_note: (kind !== 'clean' ? 'SIM ' + kind : '') }] } })));
    if (!j) return c;
    if ((j.status || '') === 'QC_EXCEPTION') step(c, 'resolve-exception', ...(await api('/receiving/exceptions/resolve/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, action: 'ACCEPT_FOR_PUTAWAY', note: 'SIM resolve ' + kind, details: [{ goods_code: goods }] } })));
    const drv = pick(['SIM-Tom', 'SIM-David']);
    step(c, 'assign-putaway-driver', ...(await api('/receiving/putaway/assign/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, driver_name: drv } })));
    await boardCheck(drv === 'SIM-Tom' ? 'T1' : 'T2', rc, { present: true, note: '被派司机应看到上架任务' });
    await boardCheck(drv === 'SIM-Tom' ? 'T2' : 'T1', rc, { present: false, note: '另一司机不应看到' });
    const put = actQ - dmg, drvK = drv === 'SIM-Tom' ? 'T1' : 'T2';
    j = step(c, 'putaway(driver)', ...(await api('/receiving/putaway/', { method: 'POST', token: S.staff[drvK].token, operator: S.staff[drvK].id, body: { receipt_no: rc, goods_code: goods, quantity: put, bin_name: pick(S.bins), driver_name: drv, idempotency_key: rc + '-P1' } })));
    if (j) {
      exp(goods).recv += put;
      if (dmg === 0) S.ledger.closedRefs.push(rc);
      else S.ledger.notes.push(`damage staging retained until disposition: ${rc}`);
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
    j = step(c, 'asn-detail', ...(await api('/asn/detail/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { asn_code: asn, supplier: 'SIM-SUP-B', goods_code: [goods], goods_qty: [qty] } })));
    if (!j) return c;
    const sns = Array.from({ length: qty }, (_, i) => `${asn}-SN${pad(i + 1, 3)}`);
    const rows = sns.map(sn => ({ goods_code: goods, serial_number: sn, goods_qty: 1 }));
    if (agent) { // pack list 经 AI-agent 通道
      let [st, pj] = await api('/asn/serial/packlists/create/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, agent: true, body: { asn_code: asn, rows, source_type: 'AI_AGENT', package_qty: qty } });
      if (st >= 400 && JSON.stringify(pj).includes('AGENT_CONFIRMATION_REQUIRED')) [st, pj] = await agentExec('/asn/serial/packlists/create/', { asn_code: asn, rows, source_type: 'AI_AGENT', package_qty: qty }, 'packlist.import', { asnCode: asn });
      step(c, 'packlist-import(agent)', st, pj);
      const docId = pj && pj.document && pj.document.id;
      if (docId) {
        const [cs, cj, meta] = await agentExec('/asn/serial/packlists/confirm/', { id: docId }, 'packlist.confirm', { resourceId: docId, asnCode: asn });
        step(c, 'packlist-confirm(agent两阶段)', cs, cj);
        if (cs === 200 && meta && meta.token) { // NEG-7:同令牌重放应返回缓存(幂等),篡改 payload 应拒
          const [rs, rj] = await api('/asn/serial/packlists/confirm/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, agent: true, body: Object.assign({}, meta.sent) });
          step(c, 'agent-replay-idempotent', rs, rj);
          const [ts, tj] = await api('/asn/serial/packlists/confirm/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, agent: true, body: Object.assign({}, meta.sent, { id: docId, note: 'tamper' }) });
          step(c, 'agent-tamper-rejected', ts, tj, true);
        }
      }
    } else {
      step(c, 'packlist-import(manual)', ...(await api('/asn/serial/packlists/create/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { asn_code: asn, rows, source_type: 'MANUAL' } })));
    }
    const aid = await listId('/asn/list/', 'asn_code', asn);
    step(c, 'arrival', ...(await api(`/asn/arrival/${aid}/`, { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: {} })));
    const slot = await freeSlot('INBOUND');
    if (slot) step(c, 'reserve-staging', ...(await api(`/asn/reserve-staging/${aid}/`, { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { staging_bin: slot } })));
    await boardCheck('WH', asn, { present: true, note: '到货后仓库应见指派卸货指示' });
    const drv = 'SIM-Leo';
    step(c, 'unload-start', ...(await api(`/asn/preload/${aid}/`, { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { unload_driver: drv, staging_bin: slot } })));
    for (const sn of sns) { const [ss, sj] = await api('/asn/serial/scan/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: { asn_code: asn, goods_code: goods, serial_number: sn } }); if (ss >= 300) { step(c, 'scan-' + sn, ss, sj); break; } }
    c.steps.push({ name: `scan×${qty}`, http: 200, ok: true, msg: '' });
    step(c, 'presort', ...(await api(`/asn/presort/${aid}/`, { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: {} })));
    step(c, 'sorted', ...(await api('/asn/sorted/', { method: 'PUT', token: S.staff.WH.token, operator: S.staff.WH.id, body: { asn_code: asn, supplier: 'SIM-SUP-B', goodsData: [{ goods_code: goods, goods_actual_qty: qty }] } })));
    const did = await listId('/asn/detail/', 'asn_code', asn);
    const j2 = step(c, 'putaway(movetobin)', ...(await api(`/asn/movetobin/${did}/`, { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { asn_code: asn, goods_code: goods, qty, bin_name: pick(S.bins), putaway_driver: 'SIM-Leo' } })));
    if (j2) { exp(goods).recv += qty; c.refs.sns = sns; c.refs.goods = goods; S.ledger.closedRefs.push(asn); }
    return c;
  }
  async function negMixing() { // NEG-1 互斥(口径修正:开放 ASN 预留计入台账;占用的暂存位测完即还)
    const c = C('NEG-mixing'); const goods = pick(S.skus.filter(s => s.includes('-L')));
    let j = step(c, 'asn-create', ...(await api('/asn/list/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { creater: 'sim' } })));
    if (!j) return c; const asn = j.asn_code; c.refs.asn = asn;
    j = step(c, 'asn-detail', ...(await api('/asn/detail/', { method: 'POST', token: S.staff.IB.token, operator: S.staff.IB.id, body: { asn_code: asn, supplier: 'SIM-SUP-B', goods_code: [goods], goods_qty: [10] } })));
    if (j) exp(goods).asnOpen = (exp(goods).asnOpen || 0) + 10; // 故意保留的开放 ASN 预留 → 期望 asn_stock 含它
    const rc1 = nid('RC'), s1 = await freeSlot('INBOUND');
    step(c, 'receiving-claim', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc1, customer: 'SIM-SUP-B', linked_asn_code: asn, staging_bins: s1 ? [s1] : [], details: [{ goods_code: goods, actual_qty: 10 }] } })));
    const s2 = await freeSlot('INBOUND');
    step(c, 'second-claim-rejected', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: nid('RC'), customer: 'SIM-SUP-B', linked_asn_code: asn, staging_bins: s2 ? [s2] : [], details: [{ goods_code: goods, actual_qty: 10 }] } })), true);
    // 归还本场景占用的暂存位,避免后续柜子无位可用
    await api('/staging/release/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { flow: 'INBOUND', reference_code: rc1 } });
    return c;
  }

  // ---------- 出仓场景 ----------
  async function outboundCommon(c, { goods, qty, sn = false, serials = [], agent = false }) {
    const tokOB = { token: S.staff.OB.token, operator: S.staff.OB.id };
    const createPayload = { customer: 'SIM-CUST-A', creater: 'sim', picking_mode: sn ? 'SN' : 'SKU_QTY', transport_required: true, ship_to: 'SIM-CUST-A Dock' };
    const createResult = agent
      ? await agentExec('/dn/list/', createPayload, 'outbound.create', tokOB)
      : await api('/dn/list/', Object.assign({ method: 'POST', body: createPayload }, tokOB));
    let j = step(c, 'dn-create' + (agent ? '(agent)' : ''), createResult[0], createResult[1]);
    if (!j) return null; const dn = j.dn_code; c.refs.dn = dn;
    const detailBody = { dn_code: dn, customer: 'SIM-CUST-A', goods_code: [goods], goods_qty: [qty] };
    if (sn) detailBody.serial_numbers = [serials];
    const detailResult = agent
      ? await agentExec('/dn/detail/', detailBody, 'outbound.detail.create', Object.assign({ resourceId: dn }, tokOB))
      : await api('/dn/detail/', Object.assign({ method: 'POST', body: detailBody }, tokOB));
    j = step(c, sn ? 'dn-detail(pick ticket' + (agent ? '·agent' : '') + ')' : 'dn-detail', detailResult[0], detailResult[1]);
    if (!j) return null;
    const id = await listId('/dn/list/', 'dn_code', dn);
    step(c, 'neworder', ...(await api(`/dn/neworder/${id}/`, Object.assign({ method: 'POST', body: {} }, tokOB))));
    step(c, 'orderrelease', ...(await api(`/dn/orderrelease/?dn_code=${encodeURIComponent(dn)}`, Object.assign({ method: 'POST', body: {} }, tokOB))));
    const [, pl] = await api(`/dn/pickinglist/${id}/`, tokOB);
    const rows = (pl && (pl.results || pl)) || [];
    const goodsData = (Array.isArray(rows) ? rows : []).filter(r => r.t_code).map(r => { const g = { t_code: r.t_code, goods_code: r.goods_code, pick_qty: r.pick_qty }; if (sn) g.serial_numbers = serials; return g; });
    if (!goodsData.length) { step(c, 'pickinglist-empty', 500, pl); return null; }
    // The production route is POST /dn/picked/<id>/ (create). The legacy PUT
    // /dn/picked/ route expects a different payload with picked_qty fields.
    const pickPayload = { dn_code: dn, goodsData };
    const pickResult = agent
      ? await agentExec(`/dn/picked/${id}/`, pickPayload, 'outbound.pick', Object.assign({ resourceId: id }, tokOB))
      : await api(`/dn/picked/${id}/`, Object.assign({ method: 'POST', body: pickPayload }, tokOB));
    step(c, 'picked' + (agent ? '(agent)' : ''), pickResult[0], pickResult[1]);
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
    const drv = pick(['SIM-Tom', 'SIM-David']), drvK = drv === 'SIM-Tom' ? 'T1' : 'T2';
    const slot = await freeSlot('OUTBOUND');
    const j = step(c, 'dispatch', ...(await api(`/dn/dispatch/${r.id}/`, { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: { dn_code: r.dn, driver: drv, staging_bin: slot || pick(S.bins) } })));
    if (!j) return c;
    exp(goods).ship += qty;
    await boardCheck(drvK, 'TR-' + r.dn, { present: true, note: '司机应看到自己的运输任务' }).catch(() => {});
    const tno = 'TR-' + r.dn;
    const [, dispatchedTransport] = await api('/transport/orders/?transport_no=' + encodeURIComponent(tno), { token: S.staff.LG.token, operator: S.staff.LG.id });
    const dispatchedOrder = ((dispatchedTransport && dispatchedTransport.results) || [])[0];
    step(c, 'driver-depart(IN_TRANSIT)', dispatchedOrder && String(dispatchedOrder.status || '').toUpperCase() === 'IN_TRANSIT' ? 200 : 500, { status: dispatchedOrder && dispatchedOrder.status });
    if (kind === 'cancelreturn') {
      step(c, 'cancel-intransit(admin)', ...(await api(`/dn/cancel-intransit/${r.id}/`, { method: 'POST', body: { cancellation_note: 'SIM 取消在途,货物退回' } })));
      const rc = nid('RC');
      const stgRet = await freeSlot('INBOUND'); // 退货收货同样需绑定暂存位
      step(c, 'return-receipt', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, customer: 'SIM-CUST-A', source_type: 'OUTBOUND_RETURN', source_reference: r.dn, staging_bins: stgRet ? [stgRet] : [], details: [{ goods_code: goods, actual_qty: qty }] } })));
      const qcBody = { receipt_no: rc, details: [{ goods_code: goods, actual_qty: qty }] };
      if (sn) qcBody.details[0].serials = serials;
      step(c, 'return-qc', ...(await api('/receiving/qc/complete/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: qcBody })));
      step(c, 'return-assign', ...(await api('/receiving/putaway/assign/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, driver_name: 'SIM-Leo' } })));
      const pj = step(c, 'return-putaway', ...(await api('/receiving/putaway/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: rc, goods_code: goods, quantity: qty, bin_name: pick(S.bins), driver_name: 'SIM-Leo', idempotency_key: rc + '-P1' } })));
      if (pj) exp(goods).ret += qty;
      step(c, 'NEG-double-return-rejected', ...(await api('/receiving/records/', { method: 'POST', token: S.staff.WH.token, operator: S.staff.WH.id, body: { receipt_no: nid('RC'), customer: 'SIM-CUST-A', source_type: 'OUTBOUND_RETURN', source_reference: r.dn, details: [{ goods_code: goods, actual_qty: qty }] } })), true);
      if (sn) S.ledger.serials.returned.push(...serials.map(s => ({ sn: s, goods })));
      S.ledger.closedRefs.push(r.dn);
      return c;
    }
    step(c, 'driver-arrive(ARRIVED)', ...(await api('/transport/transition/', { method: 'POST', token: S.staff[drvK].token, operator: S.staff[drvK].id, body: { transport_no: tno, status: 'ARRIVED' } })));
    let pod;
    if (kind === 'podexc') {
      const short = Math.max(1, Math.floor(qty * 0.1)), dmg = qty > 3 ? 1 : 0;
      step(c, 'pod-missing-note-rejected', ...(await api(`/dn/pod/${r.id}/`, { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: { dn_code: r.dn, goodsData: [{ goods_code: goods, intransit_qty: qty - short, delivery_damage_qty: dmg }] } })), true);
      pod = { dn_code: r.dn, goodsData: [{ goods_code: goods, intransit_qty: qty - short, delivery_damage_qty: dmg, delivery_note: 'SIM 短交' + short + ' 破损' + dmg }] };
    } else pod = { dn_code: r.dn, goodsData: [{ goods_code: goods, intransit_qty: qty, delivery_damage_qty: 0 }] };
    step(c, 'pod', ...(await api(`/dn/pod/${r.id}/`, { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: pod })));
    // 口径修正:POD 已自动完结运输单,不再重复提交 COMPLETED,改为查询确认终态
    const [, tj2] = await api('/transport/orders/?transport_no=' + encodeURIComponent(tno), { token: S.staff.LG.token, operator: S.staff.LG.id });
    const tOrder = ((tj2 && tj2.results) || [])[0];
    step(c, 'transport-auto-completed', tOrder && String(tOrder.status || '').toUpperCase() === 'COMPLETED' ? 200 : 500, { status: tOrder && tOrder.status });
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
    step(c, 'reallocate-shipped-sn-rejected', ...(await api('/dn/detail/', { method: 'POST', token: S.staff.OB.token, operator: S.staff.OB.id, body: { dn_code: j.dn_code, customer: 'SIM-CUST-A', goods_code: [s.goods], goods_qty: [1], serial_numbers: [[s.sn]] } })), true);
    return c;
  }
  async function negAuthz() { // NEG-8 越权抽查
    const c = C('NEG-authz');
    step(c, 'QC写财务被拒', ...(await api('/capital/', { method: 'POST', token: S.staff.QC.token, operator: S.staff.QC.id, body: { capital_name: 'SIM', capital_qty: 1, capital_cost: 1, creater: 'x' } })), true);
    step(c, '司机建员工被拒', ...(await api('/staff/', { method: 'POST', token: S.staff.T1.token, operator: S.staff.T1.id, body: { staff_name: 'SIM_ESC', staff_type: 'Manager', check_code: 111111, creater: 'x' } })), true);
    step(c, '司机B流转司机A任务被拒(空探测)', 200, { note: '已在运输场景内由 driver_name 匹配校验覆盖' });
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
        let bad = [];
        if (st.role === 'Driver') bad = items.filter(i => String(i.assignee_name || '').toLowerCase() !== st.name.toLowerCase() && (view === 'active'));
        const d1 = view === 'history' ? items.filter(i => ['inbound', 'outbound'].includes(i.category) && i.business_status === 'COMPLETED' && !S.ledger.closedRefs.includes(String(i.reference))).length : 0;
        S.ledger.roleChecks.push({ role: k + '/' + st.role, ref: `${view} 全景`, expect: st.role === 'Driver' ? '仅本人任务' : '本角色范围', ok: hs === 200 && bad.length === 0, detail: `count=${items.length}${bad.length ? ' 越界:' + bad.slice(0, 3).map(i => i.reference) : ''}${d1 ? ` KNOWN-D1×${d1}` : ''}` });
      }
    }
    console.table(S.ledger.roleChecks.slice(-20));
  }

  // ---------- 不变量对账 ----------
  async function verify() {
    console.log('%c[SIM] 对账/不变量', 'color:#08c');
    S.ledger.verify = [];
    for (const g of S.skus) {
      const e = S.ledger.stockExp[g]; if (!e) continue;
      const [, sl] = await api(`/stock/list/?goods_code=${g}`);
      const row = ((sl && sl.results) || []).find(x => x.goods_code === g) || {};
      const b = S.base[g] || { goods_qty: 0, onhand: 0, can_order: 0 };
      const want = e.recv - e.ship + e.ret;
      const checks = [
        ['goods_qty', Number(row.goods_qty || 0), b.goods_qty + want + Number(e.asnOpen || 0)],
        ['onhand', Number(row.onhand_stock || 0), b.onhand + want],
        ['can_order', Number(row.can_order_stock || 0), b.can_order + want],
        // 口径修正:故意保留的开放 ASN 预留(negMixing 等)计入期望,不再误报
        ['asn_stock', Number(row.asn_stock || 0), Number(b.asn_stock || 0) + Number(e.asnOpen || 0)],
        ['dn_stock=0', Number(row.dn_stock || 0), 0],
      ];
      for (const [nm, got, exp2] of checks) S.ledger.verify.push({ sku: g, check: nm, got, want: exp2, ok: got === exp2 });
    }
    const [, asg] = await api('/staging/assignments/');
    const activeAssignments = (Array.isArray(asg) ? asg : []).filter(a => String(a.status).toUpperCase() === 'ACTIVE');
    const act = activeAssignments.filter(a => S.ledger.closedRefs.includes(String(a.reference_code)));
    if (act.length) S.ledger.notes.push('active staging on closed refs=' + JSON.stringify(act.map(a => ({ flow: a.flow, reference_code: a.reference_code, bin_name: a.bin_name }))));
    S.ledger.verify.push({ sku: '(staging)', check: '闭环单据无残留占用', got: act.length, want: 0, ok: act.length === 0 });
    const fails = S.ledger.verify.filter(v => !v.ok);
    console.table(fails.length ? fails : S.ledger.verify.slice(0, 12));
    console.log(fails.length ? `%c❌ ${fails.length} 项不变量未过` : '%c✅ 不变量全绿', fails.length ? 'color:#c00;font-weight:bold' : 'color:#0a0;font-weight:bold');
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
  }
  function exportState() {
    const blob = new Blob([JSON.stringify({ run: S.run, when: new Date().toISOString(), cfg: CFG, ledger: S.ledger, staff: Object.fromEntries(Object.entries(S.staff).map(([k, v]) => [k, { name: v.name, role: v.role, id: v.id }])) }, null, 2)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `sim-results-${S.run}.json`; a.click();
    console.log('已导出 sim-results-' + S.run + '.json —— 请发给 Claude 分析');
  }
  async function cleanup() {
    console.log('%c[SIM] 清理(可删项)…', 'color:#08c');
    const del = async (path, key) => { const [, l] = await api(path + '?max_page=500'); for (const row of ((l && l.results) || [])) if (String(row[key] || '').startsWith('SIM')) await api(`${path}${row.id}/`, { method: 'DELETE' }); };
    for (const c of S.ledger.containers) if (c.refs.dn) { const id = await listId('/dn/list/', 'dn_code', c.refs.dn); if (id) await api(`/dn/list/${id}/`, { method: 'DELETE' }); }
    await del('/driver/', 'driver_name'); await del('/goods/', 'goods_code'); await del('/customer/', 'customer_name'); await del('/supplier/', 'supplier_name');
    const [, sf] = await api('/staff/?max_page=500');
    for (const row of ((sf && sf.results) || [])) if (String(row.staff_name || '').startsWith('SIM')) await api(`/staff/${row.id}/`, { method: 'DELETE' });
    console.log('%c[SIM] 清理完成。注意:收货单/SN 台账/库存行无删除接口,将留存(建议用独立 SIM 租户)', 'color:#e80');
  }
  const help = () => console.log(`SIM 命令:
  await SIM.seed()        建主数据+角色+司机+SKU
  await SIM.runDay(0)     冒烟10柜 | runDay(1) 40柜 | runDay(2) 异常30柜 | runDay(3) 峰值50柜
  await SIM.roles()       各角色看板指示核验(active+history)
  await SIM.verify()      库存守恒/暂存位/不变量对账
  SIM.report()            汇总表   SIM.export() 导出JSON发给Claude
  await SIM.cleanup()     删除可删的SIM数据`);
  help();
  return { seed, runDay, roles: rolesAudit, verify, report, export: exportState, cleanup, help, _state: S, _cfg: CFG };
})();
