// 文檔站外殼：依 nav.js 產生頂部第一級、左側第二級、麵包屑與頁尾。
// 版型與 class 沿用 design-system/assets/portal.css，頁面本身只寫 <main> 內容。
// 每頁在 <body> 標註 data-page（nav.js 中的 id）與 data-root（回到 docs/ 的相對路徑）。
'use strict';
(function () {
  const nav = window.DOCS_NAV;
  const body = document.body;
  const main = document.getElementById('main');
  if (!nav || !main) return;

  const root = body.dataset.root || '';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
  const icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 17.5h7m-3.5-3.5v7"/></svg>';

  let group = nav.groups[0];
  let entry = group.pages[0];
  for (const g of nav.groups) {
    for (const p of g.pages) {
      if (p.id === body.dataset.page) { group = g; entry = p; }
    }
  }

  const skip = document.createElement('a');
  skip.className = 'skip';
  skip.href = '#main';
  skip.textContent = '跳至主要內容';
  skip.addEventListener('click', (e) => {
    e.preventDefault();
    main.setAttribute('tabindex', '-1');
    main.focus();
  });

  const header = document.createElement('header');
  header.className = 'topbar';
  header.innerHTML =
    `<a class="brand" href="${root}index.html"><span class="brand-mark">${icon}</span>` +
    `<span>${esc(nav.title)}<small>${esc(nav.subtitle)}</small></span></a>` +
    `<nav class="topnav" aria-label="第一級選單">${nav.groups.map((g) =>
      `<a href="${root}${g.pages[0].href}"${g.id === group.id ? ' class="active" aria-current="true"' : ''}>${esc(g.name)}</a>`
    ).join('')}</nav>` +
    `<div class="top-end"><span class="env">${esc(nav.badge)}</span></div>`;

  const aside = document.createElement('aside');
  aside.className = 'sidebar';
  aside.id = 'sidebar';
  aside.innerHTML =
    `<div class="side-heading"><small>${esc(group.en)}</small><strong>${esc(group.name)}</strong></div>` +
    '<div class="caption">本分類頁面</div>' +
    `<nav class="sidenav" aria-label="第二級選單">${group.pages.map((p) =>
      `<a href="${root}${p.href}"${p.id === entry.id ? ' class="active" aria-current="page"' : ''}>` +
      `<span class="nav-icon">${icon}</span><span>${esc(p.name)}</span></a>`
    ).join('')}</nav>` +
    '<div class="side-foot">工程文檔 · 介面設計系統 v1.0</div>';

  const crumb = document.createElement('div');
  crumb.className = 'breadcrumb';
  crumb.innerHTML =
    '<button id="menu-toggle" class="button mobile-menu" aria-label="展開第二級選單" aria-controls="sidebar" aria-expanded="false">☰</button>' +
    `<span>文檔</span><span>›</span><span>${esc(group.name)} › ${esc(entry.name)}</span>`;

  const foot = document.createElement('footer');
  foot.className = 'page-foot';
  foot.innerHTML = '<span>瀏覽器 RPA 工程文檔</span><span>繁體中文 · 離線可讀</span>';

  body.insertBefore(skip, main);
  body.insertBefore(header, main);
  body.insertBefore(aside, main);
  main.insertBefore(crumb, main.firstChild);
  main.appendChild(foot);

  const toggle = crumb.querySelector('#menu-toggle');
  const setOpen = (open) => {
    aside.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', String(open));
  };
  toggle.addEventListener('click', () => setOpen(!aside.classList.contains('open')));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setOpen(false); });
})();
