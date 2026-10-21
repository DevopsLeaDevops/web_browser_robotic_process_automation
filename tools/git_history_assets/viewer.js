/* 全部節點保留拓撲順序；畫面只建立可見列，搜尋不刪掉中間節點。 */
(() => {
  "use strict";

  function layout(commits) {
    const available = new Set(commits.map(commit => commit.oid));
    const lanes = [];
    let width = 1;
    const free = () => {
      const index = lanes.indexOf(null);
      return index < 0 ? lanes.length : index;
    };
    const rows = commits.map(commit => {
      let lane = lanes.indexOf(commit.oid);
      if (lane < 0) lane = free();
      lanes[lane] = null;
      const segments = [];
      lanes.forEach((oid, index) => {
        if (oid) segments.push([index, index]);
      });
      commit.parents.filter(oid => available.has(oid)).forEach((parent, index) => {
        let target = lanes.indexOf(parent);
        if (target < 0) {
          target = index === 0 && lanes[lane] === null ? lane : free();
          lanes[target] = parent;
        }
        segments.push([lane, target]);
      });
      width = Math.max(width, lane + 1, lanes.length);
      while (lanes.length && lanes[lanes.length - 1] === null) lanes.pop();
      return { commit, lane, segments };
    });
    return { rows, width };
  }

  // 純拓撲函式可由 Node 驗證；瀏覽器不依賴 Node 或外部套件。
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { layout };
    return;
  }

  const payload = JSON.parse(document.getElementById("git-history-data").textContent);
  const { snapshot, messages } = payload;
  const byId = new Map(snapshot.commits.map(commit => [commit.oid, commit]));
  const refs = new Map();
  const prs = new Map();
  snapshot.refs.forEach(ref => {
    if (!refs.has(ref.oid)) refs.set(ref.oid, []);
    refs.get(ref.oid).push(ref);
  });
  snapshot.prs.forEach(pr => {
    new Set([pr.headOid, pr.mergeOid].filter(Boolean)).forEach(oid => {
      if (!prs.has(oid)) prs.set(oid, []);
      prs.get(oid).push(pr);
    });
  });
  const $ = id => document.getElementById(id);
  const scroller = $("scroller");
  const canvas = $("graph");
  const context = canvas.getContext("2d");
  const rowHeight = 50;
  const laneWidth = 22;
  let locale = payload.locale;
  let graph;
  let selected = snapshot.commits[0]?.oid;
  let matches = [];
  let matchIndex = -1;
  let frame;
  let formatter;
  let shortFormatter;

  function t(key, values = {}) {
    return (messages[locale][key] ?? key).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function date(value, short = false) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : (short ? shortFormatter : formatter).format(parsed);
  }
  function searchText(commit) {
    return [commit.oid, commit.subject, commit.body, commit.author,
      ...(refs.get(commit.oid) ?? []).map(ref => ref.name),
      ...(prs.get(commit.oid) ?? []).map(pr => `#${pr.number} ${pr.title}`)
    ].join("\n").toLocaleLowerCase();
  }
  const searchIndex = new Map(snapshot.commits.map(commit => [commit.oid, searchText(commit)]));

  function changeScope() {
    let commits = snapshot.commits;
    const root = $("scope").value;
    if (root) {
      const ancestors = new Set();
      const stack = [root];
      while (stack.length) {
        const oid = stack.pop();
        if (ancestors.has(oid)) continue;
        ancestors.add(oid);
        stack.push(...(byId.get(oid)?.parents ?? []));
      }
      commits = commits.filter(commit => ancestors.has(commit.oid));
    }
    graph = layout(commits);
    scroller.scrollTop = 0;
    scroller.scrollLeft = 0;
    if (!commits.some(commit => commit.oid === selected)) selected = commits[0]?.oid;
    $("visible-count").textContent = t("visible", { count: commits.length });
    $("spacer").style.height = `${Math.max(160, commits.length * rowHeight)}px`;
    findMatches(false);
    details();
    schedule();
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(() => { frame = null; draw(); });
  }
  function draw() {
    const graphWidth = graph.width * laneWidth + 28;
    const textWidth = Math.max(360, scroller.clientWidth - graphWidth);
    const height = scroller.clientHeight;
    const top = scroller.scrollTop;
    const start = Math.max(0, Math.floor(top / rowHeight) - 1);
    const end = Math.min(graph.rows.length, Math.ceil((top + height) / rowHeight) + 1);
    const ratio = window.devicePixelRatio || 1;
    $("spacer").style.width = `${graphWidth + textWidth}px`;
    canvas.style.top = `${top}px`;
    canvas.style.width = `${graphWidth}px`;
    canvas.style.height = `${height}px`;
    canvas.width = Math.ceil(graphWidth * ratio);
    canvas.height = Math.ceil(height * ratio);
    context.scale(ratio, ratio);
    const style = getComputedStyle(document.documentElement);
    const colors = Array.from({ length: 6 }, (_, i) => style.getPropertyValue(`--branch-${i}`).trim());
    const x = lane => 20 + lane * laneWidth;
    context.lineWidth = 2;
    for (let i = start; i < end; i++) {
      const row = graph.rows[i];
      const y = i * rowHeight + rowHeight / 2 - top;
      for (const [from, to] of row.segments) {
        context.strokeStyle = colors[to % colors.length];
        context.beginPath();
        context.moveTo(x(from), y);
        context.bezierCurveTo(x(from), y + 25, x(to), y + 25, x(to), y + rowHeight);
        context.stroke();
      }
    }
    const fragment = document.createDocumentFragment();
    for (let i = start; i < end; i++) {
      const { commit, lane } = graph.rows[i];
      const y = i * rowHeight + rowHeight / 2 - top;
      context.beginPath();
      context.arc(x(lane), y, commit.oid === selected ? 6 : 4, 0, 2 * Math.PI);
      context.fillStyle = commit.parents.length > 1 ? style.getPropertyValue("--surface") : colors[lane % colors.length];
      context.fill();
      context.strokeStyle = colors[lane % colors.length];
      context.stroke();
      const button = element("button", undefined, "commit-row");
      button.type = "button";
      button.style.top = `${i * rowHeight}px`;
      button.style.left = `${graphWidth}px`;
      button.style.width = `${textWidth}px`;
      button.dataset.oid = commit.oid;
      button.setAttribute("aria-pressed", String(commit.oid === selected));
      if ($("search").value.trim()) button.classList.add(matches.includes(i) ? "match" : "dim");
      button.append(element("span", commit.subject, "subject"));
      const metadata = element("span", undefined, "metadata");
      metadata.append(element("span", commit.oid.slice(0, 8), "oid"));
      const commitRefs = (refs.get(commit.oid) ?? []).filter(ref => ref.kind !== "pr");
      commitRefs.forEach(ref => metadata.append(element("span", ref.name, "ref")));
      (prs.get(commit.oid) ?? []).forEach(pr => metadata.append(element("span", `#${pr.number}`, "ref")));
      metadata.append(element("span", `${commit.author} · ${date(commit.committed, true)}`));
      button.append(metadata);
      button.title = `${commit.subject}\n${commit.oid}`;
      button.onclick = () => { selected = commit.oid; details(); schedule(); };
      fragment.append(button);
    }
    if (!graph.rows.length) fragment.append(element("p", t("empty")));
    $("rows").replaceChildren(fragment);
  }

  function jump(oid) {
    let index = graph.rows.findIndex(row => row.commit.oid === oid);
    if (index < 0) {
      $("scope").value = "";
      changeScope();
      index = graph.rows.findIndex(row => row.commit.oid === oid);
    }
    if (index < 0) return;
    selected = oid;
    scroller.scrollTop = Math.max(0, index * rowHeight - scroller.clientHeight / 3);
    details();
    schedule();
  }
  function details() {
    const panel = $("details");
    const commit = byId.get(selected);
    panel.replaceChildren(element("h2", commit?.subject ?? t("empty")));
    if (!commit) return;
    const info = element("dl");
    [["hash", commit.oid], ["author", commit.author], ["authored", date(commit.authored)],
      ["committed", date(commit.committed)]].forEach(([key, value]) => {
      info.append(element("dt", t(key)), element("dd", value));
    });
    panel.append(info, element("h3", t("parents")));
    const parents = element("div", undefined, "chips");
    commit.parents.forEach(oid => {
      const button = element("button", oid.slice(0, 8));
      button.type = "button";
      button.disabled = !byId.has(oid);
      button.title = byId.get(oid)?.subject ?? t("missing");
      button.onclick = () => jump(oid);
      parents.append(button);
    });
    panel.append(commit.parents.length ? parents : element("p", t("root")));
    const names = refs.get(commit.oid) ?? [];
    if (names.length) {
      panel.append(element("h3", t("references")), element("p", names.map(ref => ref.name).join(" · ")));
    }
    if (commit.body.trim()) panel.append(element("h3", t("message")), element("pre", commit.body));
    const related = prs.get(commit.oid) ?? [];
    if (related.length) panel.append(element("h3", t("pullRequests")));
    related.forEach(pr => {
      const item = element("div", undefined, "pr-item");
      const link = element("a", `#${pr.number} ${pr.title}`);
      link.href = pr.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      item.append(link, element("small", `${t(pr.state)} · ${pr.head} → ${pr.base}`));
      item.append(element("small", t(commit.oid === pr.mergeOid ? "mergeResult" : "prHead")));
      if (pr.mergeOid && pr.mergeOid !== commit.oid && byId.has(pr.mergeOid)) {
        const button = element("button", t("goMerge"));
        button.onclick = () => jump(pr.mergeOid);
        item.append(button);
      }
      panel.append(item);
    });
  }
  function findMatches(jumpFirst) {
    const query = $("search").value.trim().toLocaleLowerCase();
    matches = query ? graph.rows.flatMap((row, index) => searchIndex.get(row.commit.oid).includes(query) ? [index] : []) : [];
    matchIndex = -1;
    if (jumpFirst && matches.length) stepMatch(1);
    else updateMatches();
    schedule();
  }
  function updateMatches() {
    $("match-count").textContent = $("search").value.trim() ? t("matches", { current: matchIndex + 1, count: matches.length }) : "";
    $("previous").disabled = $("next").disabled = !matches.length;
  }
  function stepMatch(delta) {
    if (!matches.length) return;
    matchIndex = (matchIndex + delta + matches.length) % matches.length;
    jump(graph.rows[matches[matchIndex]].commit.oid);
    updateMatches();
  }
  function translate() {
    document.documentElement.lang = locale;
    $("language").value = locale;
    let zone = payload.timezone;
    try { new Intl.DateTimeFormat(locale, { timeZone: zone }); } catch { zone = "UTC"; }
    formatter = new Intl.DateTimeFormat(locale, { timeZone: zone, dateStyle: "medium", timeStyle: "short" });
    shortFormatter = new Intl.DateTimeFormat(locale, { timeZone: zone, month: "2-digit", day: "2-digit", year: "numeric" });
    document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = t(node.dataset.i18n); });
    document.title = `${snapshot.name} · ${t("history")}`;
    $("repo-name").textContent = snapshot.name;
    $("summary").textContent = t("summary", { commits: snapshot.commits.length, refs: snapshot.refs.length, prs: snapshot.prs.length });
    $("snapshot-note").textContent = t("snapshot", { date: date(snapshot.generated), zone }) + " · " + t(snapshot.fetched ? "fetched" : "cached");
    $("search").placeholder = t("searchHint");
    const warnings = [];
    if (snapshot.shallow) warnings.push(t("shallow"));
    const missing = snapshot.prs.filter(pr => !byId.has(pr.headOid)).length;
    if (missing) warnings.push(t("missingHeads", { count: missing }));
    $("warning").textContent = warnings.join(" ");
    $("warning").hidden = !warnings.length;
    const chosen = $("scope").value;
    const all = element("option", t("all"));
    all.value = "";
    $("scope").replaceChildren(all);
    for (const kind of ["remote", "branch", "tag", "pr", "head", "other"]) {
      const group = element("optgroup");
      group.label = t(kind);
      snapshot.refs.filter(ref => ref.kind === kind).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })).forEach(ref => {
        const option = element("option", ref.name);
        option.value = ref.oid;
        group.append(option);
      });
      if (group.children.length) $("scope").append(group);
    }
    $("scope").value = chosen;
    $("refresh-command").textContent = `python tools/git_history.py --fetch${snapshot.github ? " --github" : ""} --lang ${locale} --timezone ${zone} --open`;
    changeScope();
  }

  $("scope").onchange = changeScope;
  $("language").onchange = () => { locale = $("language").value; translate(); };
  $("search").oninput = () => findMatches(true);
  $("search").onkeydown = event => { if (event.key === "Enter") stepMatch(event.shiftKey ? -1 : 1); };
  $("previous").onclick = () => stepMatch(-1);
  $("next").onclick = () => stepMatch(1);
  scroller.tabIndex = 0;
  scroller.addEventListener("scroll", schedule, { passive: true });
  scroller.addEventListener("click", event => {
    if (event.target.closest("button")) return;
    const index = Math.floor((event.clientY - scroller.getBoundingClientRect().top + scroller.scrollTop) / rowHeight);
    if (graph.rows[index]) { selected = graph.rows[index].commit.oid; details(); schedule(); }
  });
  scroller.addEventListener("keydown", event => {
    let index = graph.rows.findIndex(row => row.commit.oid === selected);
    if (event.key === "ArrowDown") index++;
    else if (event.key === "ArrowUp") index--;
    else if (event.key === "Home") index = 0;
    else if (event.key === "End") index = graph.rows.length - 1;
    else return;
    event.preventDefault();
    if (graph.rows[index]) jump(graph.rows[index].commit.oid);
  });
  window.addEventListener("resize", schedule);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", schedule);
  translate();
})();
