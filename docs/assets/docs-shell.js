// 文檔站外殼：依 nav.js 產生頂部第一級、左側第二級、語言切換、麵包屑與頁尾。
// 版型與 class 沿用 design-system/assets/portal.css，頁面本身只寫 <main> 內容。
// 每頁在 <html> 標註 lang（zh-Hant、zh-Hans、en），在 <body> 標註 data-page（nav.js 中的 id）
// 與 data-root（回到該語言根目錄的相對路徑：繁中是 docs/，其他語言是 docs/<語言>/）。
'use strict';
(function () {
  const nav = window.DOCS_NAV;
  const body = document.body;
  const main = document.getElementById('main');
  if (!nav || !main) return;

  const locale = document.documentElement.lang || nav.default;
  const pick = (value) => (value && typeof value === 'object' ? value[locale] ?? value[nav.default] : value);
  const text = (key) => pick(nav.text[key]);
  const root = body.dataset.root || '';
  // 預設語言（繁中）在 docs/，其他語言在 docs/<語言>/，各語言的目錄結構相同
  const docsRoot = locale === nav.default ? root : `${root}../`;
  const rootOf = (code) => (code === nav.default ? docsRoot : `${docsRoot}${code}/`);
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
  const current = nav.languages.find((l) => l.code === locale) || nav.languages[0];

  const skip = document.createElement('a');
  skip.className = 'skip';
  skip.href = '#main';
  skip.textContent = text('skip');
  skip.addEventListener('click', (e) => {
    e.preventDefault();
    main.setAttribute('tabindex', '-1');
    main.focus();
  });

  const languages = nav.languages.map((l) =>
    `<a href="${rootOf(l.code)}${entry.href}" lang="${l.code}" hreflang="${l.code}" title="${esc(l.label)}"` +
    `${l.code === locale ? ' class="active" aria-current="true"' : ''}>` +
    `<span class="lang-full">${esc(l.label)}</span><span class="lang-short" aria-hidden="true">${esc(l.short)}</span></a>`
  ).join('');

  const header = document.createElement('header');
  header.className = 'topbar';
  header.innerHTML =
    `<a class="brand" href="${root}index.html"><span class="brand-mark">${icon}</span>` +
    `<span>${esc(text('title'))}<small>${esc(nav.subtitle)}</small></span></a>` +
    `<nav class="topnav" aria-label="${esc(text('topnav'))}">${nav.groups.map((g) =>
      `<a href="${root}${g.pages[0].href}"${g.id === group.id ? ' class="active" aria-current="true"' : ''}>${esc(pick(g.name))}</a>`
    ).join('')}</nav>` +
    `<div class="top-end"><nav class="segmented lang-switch" aria-label="${esc(text('language'))}">${languages}</nav>` +
    `<span class="env">${esc(text('badge'))}</span></div>`;

  // 切換語言時保留目前的錨點：各語言頁面的 id 相同
  header.querySelectorAll('.lang-switch a').forEach((link) => {
    link.addEventListener('click', () => {
      link.href = link.getAttribute('href').split('#')[0] + window.location.hash;
    });
  });

  const aside = document.createElement('aside');
  aside.className = 'sidebar';
  aside.id = 'sidebar';
  aside.innerHTML =
    `<div class="side-heading"><small>${esc(group.caption)}</small><strong>${esc(pick(group.name))}</strong></div>` +
    `<div class="caption">${esc(text('sideCaption'))}</div>` +
    `<nav class="sidenav" aria-label="${esc(text('sidenav'))}">${group.pages.map((p) =>
      `<a href="${root}${p.href}"${p.id === entry.id ? ' class="active" aria-current="page"' : ''}>` +
      `<span class="nav-icon">${icon}</span><span>${esc(pick(p.name))}</span></a>`
    ).join('')}</nav>` +
    `<div class="side-foot">${esc(text('sideFoot'))}</div>`;

  const crumb = document.createElement('div');
  crumb.className = 'breadcrumb';
  crumb.innerHTML =
    `<button id="menu-toggle" class="button mobile-menu" aria-label="${esc(text('menu'))}" aria-controls="sidebar" aria-expanded="false">☰</button>` +
    `<span>${esc(text('crumb'))}</span><span>›</span><span>${esc(pick(group.name))} › ${esc(pick(entry.name))}</span>`;

  const foot = document.createElement('footer');
  foot.className = 'page-foot';
  foot.innerHTML = `<span>${esc(text('footName'))}</span><span>${esc(current.label)} · ${esc(text('footNote'))}</span>`;

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
