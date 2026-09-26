// ==UserScript==
// @name         Educoder 答案导入导出
// @namespace    educoder-local-answers
// @version      0.3.1
// @description  仅导出当前关卡的答案数组，导入后直接勾选页面选项，浮窗支持拖动。
// @match        https://www.educoder.net/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(() => {
  'use strict';
  const tasks = new Map();
  let panel, info, importing = false;
  let message = '请刷新关卡读取已保存答案。';
  const check = (condition, reason) => { if (!condition) throw new Error(reason); };
  const pageTask = () => location.pathname.startsWith('/tasks/')
    ? location.pathname.split('/').filter(Boolean).at(-1) : null;

  function answers(value) {
    check(Array.isArray(value) && value.length > 0 && value.length <= 1000
      && value.every(item => typeof item === 'string' && item.trim().length > 0 && item.length <= 10000),
    '答案必须是非空字符串数组，例如 ["B","C"]。');
    return [...value];
  }

  function endpoint(value) {
    try {
      const url = new URL(value, location.href);
      if (url.origin !== 'https://data.educoder.net') return null;
      const match = url.pathname.match(/^\/api\/tasks\/([\w-]+)(\/choose_build)?\.json$/);
      return match && { task: match[1], submit: Boolean(match[2]) };
    } catch { return null; }
  }

  function readOutputs(data, count) {
    check(Array.isArray(data?.test_sets) && data.test_sets.length === count, '当前关卡的答案尚不完整。');
    const rows = [...data.test_sets].sort((a, b) => a.position - b.position);
    check(rows.every((row, i) => row.position === i + 1), '无法识别答案顺序。');
    return answers(rows.map(row => row.actual_output));
  }

  function observe(meta, method, data) {
    if (!meta || !data || typeof data !== 'object') return;
    try {
      if (!meta.submit && method === 'GET' && data.game?.identifier === meta.task) {
        // 仅读取任务标识、答案数量和答案，不处理题干或选项。
        const count = data.choose_test_cases?.challenge_chooses_count;
        if (!Number.isInteger(count) || count <= 0 || data.challenge?.id == null) return;
        const context = { title: data.challenge.subject, count, answer: null, sizes: [...(data.chooses || [])].sort((a, b) => a.position - b.position).map(q => q.challenge_question.length) };
        tasks.set(meta.task, context);
        message = '当前关卡已读取，可以导入答案。';
        if (data.choose_test_cases.had_submmit || data.choose_test_cases.had_all_submmit) {
          context.answer = readOutputs(data.choose_test_cases, count);
          message = '已读取当前关卡的已提交答案，可以导出。';
        }
      } else if (meta.submit && method === 'POST' && tasks.has(meta.task) && Array.isArray(data.test_sets)) {
        const context = tasks.get(meta.task);
        context.answer = null;
        context.answer = readOutputs(data, context.count);
        message = '已更新本次提交的答案，可以导出。';
      }
    } catch (error) { message = error.message; }
    render();
  }

  function groups(context) {
    const visible = node => node.getClientRects().length > 0;
    const controls = node => [...node.querySelectorAll('input[type="radio"],input[type="checkbox"]')];
    let result = [...document.querySelectorAll('.ant-radio-group,.ant-checkbox-group,[role="radiogroup"],[role="group"]')]
      .filter(node => visible(node) && controls(node).length)
      .filter(node => ![...node.children].some(child => child.querySelector('.ant-radio-group,.ant-checkbox-group,[role="radiogroup"]')))
      .map(controls);
    if (result.length !== context.count) {
      // 标准控件没有 group 容器时，只接受最小共同父容器中的精确选项数量。
      const inputs = [...document.querySelectorAll('input[type="radio"],input[type="checkbox"]')]
        .filter(node => visible(node) || visible(node.closest('label') || node));
      result = [];
      let cursor = 0;
      for (const size of context.sizes) {
        let parent = inputs[cursor]?.parentElement;
        while (parent && controls(parent).length < size) parent = parent.parentElement;
        if (!parent || controls(parent).length !== size) break;
        const found = controls(parent);
        if (!found.every((node, i) => node === inputs[cursor + i])) break;
        result.push(found); cursor += size;
      }
      check(cursor === inputs.length, '无法可靠定位选项容器，请提供一道题的外层 HTML。');
    }
    check(result.length === context.count, '页面题目数量不匹配，请等待题目加载完成。');
    check(new Set(result.flat()).size === result.flat().length, '页面选项容器存在重复，无法导入。');
    if (context.sizes.length === context.count) check(result.every((list, i) => list.length === context.sizes[i]), '页面选项数量不匹配。');
    return result;
  }

  async function fill(value) {
    const path = location.pathname, context = tasks.get(pageTask());
    check(context && context.count === value.length, '请刷新关卡，并确认答案数量与题目数量一致。');
    const targets = value.map(answer => {
      const text = answer.trim().toUpperCase();
      check(/^[A-Z](?:[ ,，;；]*[A-Z])*$/.test(text), '无法识别答案字母格式。');
      return new Set([...text.matchAll(/[A-Z]/g)].map(match => match[0].charCodeAt(0) - 65));
    });
    const initial = groups(context);
    initial.forEach((list, i) => {
      check([...targets[i]].every(index => index < list.length), `第 ${i + 1} 题答案超出选项范围。`);
      check(!list.some(node => node.disabled), `第 ${i + 1} 题选项不可编辑。`);
      check(list.every(node => node.type === list[0].type), '选项类型不一致。');
      check(list[0].type !== 'radio' || targets[i].size === 1, `第 ${i + 1} 题为单选题。`);
    });
    // 使用控件原生点击触发 React/Ant Design 的 onChange，更新页面状态。
    // 每次点击后重新定位，避免重渲染后继续操作已脱离页面的节点。
    for (let i = 0; i < targets.length; i++) {
      for (let j = 0; j < initial[i].length; j++) {
        check(location.pathname === path, '已切换关卡，停止导入。');
        const node = groups(context)[i][j], wanted = targets[i].has(j);
        if (node.checked !== wanted && (node.type === 'checkbox' || wanted)) {
          node.click();
          await new Promise(resolve => setTimeout(resolve, 40));
        }
      }
    }
    await new Promise(resolve => setTimeout(resolve, 100));
    check(location.pathname === path, '已切换关卡，停止导入。');
    check(groups(context).every((list, i) => list.every((node, j) => node.checked === targets[i].has(j))),
      '页面没有保留全部选择，可能已有部分选项更新，请检查页面并提供选项 HTML。');
  }

  const originalFetch = window.fetch;
  window.fetch = async function(input, init) {
    const request = input instanceof Request;
    const meta = endpoint(request ? input.url : String(input));
    const method = String(init?.method || (request ? input.method : 'GET')).toUpperCase();
    const response = await originalFetch.call(this, input, init);
    if (meta && response.ok) response.clone().json().then(data => observe(meta, method, data)).catch(() => {});
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  const requests = new WeakMap();
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    const result = originalOpen.call(this, method, url, ...rest);
    requests.set(this, { meta: endpoint(url), method: String(method).toUpperCase() });
    return result;
  };
  XMLHttpRequest.prototype.send = function(body) {
    const request = requests.get(this);
    if (request?.meta) this.addEventListener('load', () => {
      if (this.status < 200 || this.status >= 300) return;
      try {
        observe(request.meta, request.method, this.responseType === 'json' ? this.response : JSON.parse(this.responseText));
      } catch { /* 忽略非 JSON 响应。 */ }
    }, { once: true });
    return originalSend.call(this, body);
  };

  function render() {
    if (!panel) return;
    panel.hidden = !pageTask();
    info.textContent = message;
  }


  function mount() {
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:2147483647';
    const root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = `<style>
      :host{font:14px/1.5 system-ui;color:#172033}details{width:min(310px,calc(100vw - 48px));background:#fff;border:1px solid #ccd3df;border-radius:10px;box-shadow:0 4px 24px #0003;padding:12px}summary{cursor:move;font-weight:bold;touch-action:none;user-select:none}p{white-space:pre-wrap;overflow-wrap:anywhere}button{margin:4px 4px 4px 0;padding:6px 9px;cursor:pointer}button:disabled{cursor:default}input{display:none}
      </style><details open><summary>答案导入 / 导出</summary><p></p><nav></nav><input type="file" accept=".json,application/json"></details>`;
    panel = root.querySelector('details'); info = root.querySelector('p');
    const nav = root.querySelector('nav'), file = root.querySelector('input');
    function button(label, action) {
      const node = document.createElement('button'); node.textContent = label;
      node.addEventListener('click', action); nav.append(node); return node;
    }
    button('导出当前答案', () => {
      const value = tasks.get(pageTask())?.answer;
      if (!value) { message = '请先刷新已作答的关卡，等待读取完整答案。'; render(); return; }
      const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
      const title = String(tasks.get(pageTask())?.title || 'educoder-answers')
        .replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g, '_').trim().replace(/[. ]+$/g, '').slice(0, 100);
      const filename = !title || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(title)
        ? `关卡-${title || '答案'}` : title;
      const link = document.createElement('a'); link.href = url; link.download = `${filename}.json`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
    });
    button('导入答案', () => file.click());
    file.addEventListener('change', async () => {
      const selected = file.files[0]; file.value = ''; if (!selected) return;
      if (importing) return;
      importing = true;
      const importPath = location.pathname;
      try {
        check(selected.size <= 1024 * 1024, '文件不能超过 1 MB。');
        const value = answers(JSON.parse(await selected.text()));
        check(location.pathname === importPath, '已切换关卡，请重新导入。');
        message = '正在更新页面选择…'; render();
        await fill(value);
        message = `已更新 ${value.length} 道题的选择，可直接使用平台提交按钮。`;
      } catch (error) { message = `导入失败：${error.message}`; }
      finally { importing = false; }
      render();
    });
    const handle = root.querySelector('summary');
    let drag = null, moved = false;
    const place = (x, y) => {
      const rect = host.getBoundingClientRect();
      host.style.left = `${Math.max(0, Math.min(x, innerWidth - rect.width))}px`;
      host.style.top = `${Math.max(0, Math.min(y, innerHeight - rect.height))}px`;
      host.style.right = 'auto'; host.style.bottom = 'auto';
    };
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      const rect = host.getBoundingClientRect(); moved = false;
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top };
      handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener('pointermove', event => {
      if (!drag || drag.id !== event.pointerId) return;
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      if (moved) place(drag.left + dx, drag.top + dy);
    });
    const end = () => { drag = null; };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
    handle.addEventListener('lostpointercapture', end);
    handle.addEventListener('click', event => { if (moved) { event.preventDefault(); moved = false; } });
    window.addEventListener('resize', () => {
      if (!panel.hidden) { const rect = host.getBoundingClientRect(); place(rect.left, rect.top); }
    });
    document.body.append(host); render();
    let path = location.pathname;
    setInterval(() => {
      if (path !== location.pathname) {
        path = location.pathname;
        message = '已切换关卡，请重新导入对应答案。'; render();
      }
    }, 500);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
