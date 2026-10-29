"use strict";
/* review-desk page: read the paper, judge each comment, hand edits to the agent, draft replies. */

const T = {
  en: {
    inbox: "Inbox", comments: "Comments", notes: "Notes",
    export_md: "Response .md", export_tex: "Response .tex",
    st_todo: "To do", st_analyzing: "Analyzing", st_revised: "Revised", st_replied: "Replied",
    rc_misread: "Reviewer misread", rc_our_error: "We wrote it wrong", rc_weak_evidence: "Evidence too weak",
    rc_structure: "Structure invites misreading", rc_other: "Other",
    needs_you: "Needs your decision", with_agent: "With the agent", open_comments: "Open comments",
    anchor_report: "Anchors not found in the paper", nothing: "Nothing waiting. All comments replied.",
    no_notes: "No notes yet. Select text in the paper to write one.",
    root_cause: "Root cause (why did the reviewer say this?)", root_note: "One line on the root cause",
    response: "Reply to the reviewer (draft)", changes: "Changes made in the manuscript",
    ask: "Instruction for the agent about this comment…", send: "Send to agent", locate: "Show in paper",
    note_btn: "Note", cancel: "Cancel", note_ph: "What should change here? (goes to the agent)",
    general: "Not about a specific comment",
    ag_on: "Agent listening", ag_poll: "Agent polled", ag_off: "No agent connected",
    no_agent: "Notes are waiting but no agent is listening. Tell your agent to run",
    copy: "Copy", copied: "Copied", go: "Go ahead", reject: "Don't change", answer: "Answer",
    answer_ph: "Your answer…", follow: "Follow up", you: "You", agent: "Agent",
    a_unmatched: "anchor lost", a_guessed: "guessed spot", a_fuzzy: "fuzzy", a_none: "no anchor",
    reviewer: "Reviewer", replied_of: "replied", saved: "saved", line: "line",
    proposal: "Proposal", question: "Question for you", build_err: "Build error (showing last good build):",
    rebuilt: "Paper rebuilt", more: "details", sent: "Sent to the agent",
  },
  zh: {
    inbox: "待办", comments: "审稿意见", notes: "批注",
    export_md: "回复信 .md", export_tex: "回复信 .tex",
    st_todo: "未处理", st_analyzing: "分析中", st_revised: "已改", st_replied: "已回复",
    rc_misread: "审稿人误读", rc_our_error: "我们写错", rc_weak_evidence: "证据不足",
    rc_structure: "结构致误读", rc_other: "其他",
    needs_you: "等你决定", with_agent: "agent 处理中", open_comments: "未回复的意见",
    anchor_report: "原文中找不到锚点的意见", nothing: "没有待办，全部意见已回复。",
    no_notes: "还没有批注。在论文里选中文字即可写批注。",
    root_cause: "根因：审稿人为什么这么说？", root_note: "一句话写清根因",
    response: "给审稿人的回复（草稿）", changes: "稿件里改了什么",
    ask: "关于这条意见，交代 agent 做什么……", send: "发给 agent", locate: "在原文中定位",
    note_btn: "批注", cancel: "取消", note_ph: "这里要怎么改？（会发给 agent）",
    general: "不针对某条意见",
    ag_on: "agent 在监听", ag_poll: "agent 刚轮询过", ag_off: "没有 agent 连接",
    no_agent: "有批注在等，但没有 agent 在监听。让你的 agent 运行",
    copy: "复制", copied: "已复制", go: "执行", reject: "不改", answer: "回复",
    answer_ph: "你的回复……", follow: "追问", you: "我", agent: "agent",
    a_unmatched: "锚点失效", a_guessed: "推测位置", a_fuzzy: "模糊匹配", a_none: "无锚点",
    reviewer: "审稿人", replied_of: "已回复", saved: "已保存", line: "行",
    proposal: "提议", question: "需要你回答", build_err: "构建出错（显示上一次成功的构建）：",
    rebuilt: "论文已重建", more: "详情", sent: "已发给 agent",
  },
};

let S = null, lang = "en", built = null, tab = "inbox", focus = null, pending = false;
const opened = new Set();
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const t = (k) => (T[lang] && T[lang][k]) || T.en[k] || k;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.status);
  return d;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 1600);
}

/* ------------------------------------------------------------ state loop */

async function refresh() {
  let s;
  try { s = await api("api/state"); } catch (e) { return; }
  const sig = (x) => x ? JSON.stringify([x.comments, x.notes, x.report]) : "";
  const changed = sig(s) !== sig(S);
  S = s; lang = s.lang || "en";
  document.documentElement.lang = lang;
  if (s.build_id !== built) {
    const first = built === null;
    await loadPaper();
    if (!first) toast(t("rebuilt"));
  }
  renderTop();
  if (changed || pending) {
    if (editing()) pending = true; else { pending = false; renderPanel(); }
  }
}

function editing() {
  const a = document.activeElement;
  return a && $("#panel").contains(a) && /^(TEXTAREA|INPUT)$/.test(a.tagName);
}

/* ------------------------------------------------------------ paper */

async function loadPaper() {
  const p = await api("api/paper");
  const box = $("#paper"), y = box.scrollTop;
  const parts = [`<h1 class="title">${S.title}</h1>`];
  for (const b of p.blocks) {
    parts.push(`<div class="blk ${b.kind}" id="${b.id}" data-line="${b.line}" data-cids="${esc(b.cids.join(" "))}">${b.html}</div>`);
  }
  box.innerHTML = parts.join("");
  const macros = {};
  for (const [k, v] of Object.entries(S.macros || {})) macros["\\" + k] = v;
  if (window.katex) {
    for (const el of $$(".rd-m, .rd-md", box)) {
      try {
        katex.render(el.textContent, el, { displayMode: el.classList.contains("rd-md"), throwOnError: false, macros, trust: false });
      } catch (e) { /* leave the TeX visible */ }
    }
  }
  for (const el of $$(".rd-fig[data-src]", box)) {
    const img = new Image();
    img.alt = el.dataset.src;
    img.onload = () => { el.textContent = ""; el.appendChild(img); el.classList.add("has-img"); };
    img.src = "figures/" + encodeURIComponent(el.dataset.src);
  }
  box.scrollTop = y;
  built = p.build_id;
  if (focus) markOn(focus);
}

function marksOf(cid) {
  return [...$$(`mark.rd-mark[data-cid="${CSS.escape(cid)}"]`),
          ...$$(".blk").filter((b) => b.dataset.cids.split(" ").includes(cid))];
}

function markOn(cid) {
  $$(".on", $("#paper")).forEach((e) => e.classList.remove("on"));
  if (cid) marksOf(cid).forEach((e) => e.classList.add("on"));
}

function locate(target) {
  const el = target.startsWith("b") && $("#" + target) ? $("#" + target) : marksOf(target)[0];
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  const blk = el.closest(".blk");
  if (blk) { blk.classList.remove("flash"); void blk.offsetWidth; blk.classList.add("flash"); }
}

function focusComment(cid) {
  focus = cid;
  opened.add(cid);
  const inInbox = S.comments.some((c) => c.id === cid && c.status !== "replied");
  if (!(tab === "comments" || (tab === "inbox" && inInbox))) tab = "comments";
  renderPanel();
  markOn(cid);
  const card = $(`.card[data-cid="${CSS.escape(cid)}"]`);
  if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("#paper").addEventListener("click", (e) => {
  if (String(window.getSelection())) return;
  const m = e.target.closest("mark.rd-mark");
  if (m) return focusComment(m.dataset.cid);
  const b = e.target.closest(".blk");
  if (b && b.dataset.cids) focusComment(b.dataset.cids.split(" ")[0]);
});

/* ------------------------------------------------------------ top bar */

function renderTop() {
  $("#doc-title").textContent = S.title.replace(/<[^>]+>/g, "");
  document.title = "review-desk · " + $("#doc-title").textContent;
  const n = S.comments.length || 1, cnt = {};
  for (const s of S.statuses) cnt[s] = 0;
  for (const c of S.comments) cnt[c.status] = (cnt[c.status] || 0) + 1;
  const bar = S.statuses.map((s) => `<span style="width:${100 * cnt[s] / n}%;background:var(--${s})" title="${t("st_" + s)}: ${cnt[s]}"></span>`).join("");
  $("#progress").innerHTML = `<div class="bar">${bar}</div><span>${cnt.replied}/${S.comments.length} ${t("replied_of")}</span>`;
  const a = S.agent, ag = $("#agent");
  const recent = a.last_poll && a.now - a.last_poll < 90;
  ag.className = "agent" + (a.listening ? " on" : recent ? " poll" : "");
  ag.textContent = a.listening ? t("ag_on") : recent ? t("ag_poll") : t("ag_off");
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  const waiting = S.notes.some((x) => x.status === "new");
  const bn = $("#banner");
  if (S.build_error) {
    bn.hidden = false; bn.textContent = t("build_err") + " " + S.build_error;
  } else if (waiting && !a.listening && !recent) {
    const cmd = "review-desk wait --no-block";
    bn.hidden = false;
    bn.innerHTML = `${esc(t("no_agent"))} <code>${cmd}</code><button class="ghost" id="cp">${esc(t("copy"))}</button>`;
    $("#cp").onclick = () => navigator.clipboard.writeText(cmd).then(() => toast(t("copied")));
  } else bn.hidden = true;
  const open = S.notes.filter((x) => x.status === "hold").length + S.comments.filter((c) => c.status !== "replied").length;
  for (const b of $$("#tabs button")) {
    const k = b.dataset.tab;
    b.classList.toggle("on", k === tab);
    b.innerHTML = esc(t(k)) + (k === "inbox" && open ? `<span class="n">${open}</span>` : "");
  }
}

$("#tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  tab = b.dataset.tab; renderTop(); renderPanel();
});

/* ------------------------------------------------------------ side panel */

function renderPanel() {
  const P = $("#panel"), y = P.scrollTop;
  let h = "";
  if (tab === "inbox") {
    const hold = S.notes.filter((n) => n.status === "hold");
    const busy = S.notes.filter((n) => n.status === "new" || n.status === "working");
    const open = S.comments.filter((c) => c.status !== "replied");
    if (hold.length) h += sec(t("needs_you")) + hold.map(noteCard).join("");
    if (busy.length) h += sec(t("with_agent")) + busy.map(noteCard).join("");
    if (open.length) h += sec(t("open_comments")) + open.map(commentCard).join("");
    if (S.report.length) h += sec(t("anchor_report")) + S.report.map((r) =>
      `<div class="card"><div class="head"><span class="cid">${esc(r.comment)}</span><span class="badge unmatched">${esc(t("a_unmatched"))}</span></div><div class="quote">${esc(r.anchors.join("\n"))}</div></div>`).join("");
    if (!hold.length && !busy.length && !open.length) h += `<div class="empty">${esc(t("nothing"))}</div>`;
  } else if (tab === "comments") {
    let last = null;
    for (const c of S.comments) {
      if (c.reviewer !== last) { h += sec(t("reviewer") + " " + c.reviewer); last = c.reviewer; }
      h += commentCard(c);
    }
  } else {
    const ns = [...S.notes].reverse();
    h = ns.length ? ns.map(noteCard).join("") : `<div class="empty">${esc(t("no_notes"))}</div>`;
  }
  P.innerHTML = h;
  P.scrollTop = y;
}

const sec = (s) => `<div class="sec-h">${esc(s)}</div>`;

function commentCard(c) {
  const isOpen = focus === c.id || opened.has(c.id);
  const anchor = c.anchor_status === "ok" ? "" : `<span class="badge ${c.anchor_status}">${esc(t("a_" + c.anchor_status))}</span>`;
  const related = S.notes.filter((n) => n.comment === c.id);
  const st = S.statuses.map((s) => `<button class="${s}${c.status === s ? " on" : ""}" data-act="status" data-v="${s}">${esc(t("st_" + s))}</button>`).join("");
  const rc = S.root_causes.map((r) => `<button class="${c.root_cause === r ? "on" : ""}" data-act="root" data-v="${r}">${esc(t("rc_" + r))}</button>`).join("");
  return `<div class="card${focus === c.id ? " focus" : ""}${isOpen ? " open" : ""}" data-cid="${esc(c.id)}">
    <div class="head"><span class="cid">${esc(c.id)}</span>${anchor}<span class="sp"></span>
      ${c.blocks.length ? `<button class="locate" data-act="locate">${esc(t("locate"))}</button>` : ""}
      <span class="pill ${c.status}">${esc(t("st_" + c.status))}</span></div>
    <div class="txt">${esc(c.text)}</div>
    ${isOpen ? "" : `<button class="toggle" data-act="open">▸ ${esc(t("more"))}${c.root_cause ? " · " + esc(t("rc_" + c.root_cause)) : ""}${c.response ? " · ✎" : ""}</button>`}
    <div class="more">
      <div class="seg status">${st}</div>
      <div class="lbl">${esc(t("root_cause"))}</div>
      <div class="seg">${rc}</div>
      <input type="text" data-field="root_cause_note" placeholder="${esc(t("root_note"))}" value="${esc(c.root_cause_note)}">
      <div class="lbl">${esc(t("response"))}</div>
      <textarea rows="3" data-field="response">${esc(c.response)}</textarea>
      <div class="lbl">${esc(t("changes"))}</div>
      <textarea rows="2" data-field="changes">${esc(c.changes)}</textarea>
      <div class="row"><span class="saved">${esc(t("saved"))}</span></div>
      <textarea rows="2" class="ask" placeholder="${esc(t("ask"))}"></textarea>
      <div class="row"><span class="sp"></span><button class="primary" data-act="ask">${esc(t("send"))}</button></div>
      ${related.map((n) => noteMini(n)).join("")}
    </div></div>`;
}

function noteMini(n) {
  return `<div class="reply"><b><span class="pill ${n.status}">${esc(n.status)}</span> ${esc(n.title || n.text.slice(0, 60))}</b>${esc(n.reply || "")}</div>`;
}

function noteCard(n) {
  const who = n.author === "agent" ? t("agent") : t("you");
  const kind = n.status === "hold" ? (n.author === "agent" ? t("proposal") : t("question")) : "";
  const where = n.line ? `${t("line")} ${n.line}` : "";
  let acts = "";
  if (n.status === "hold") {
    acts = `<textarea rows="2" class="ans" placeholder="${esc(t("answer_ph"))}"></textarea>
      <div class="row">${n.author === "agent" ? `<button class="primary" data-act="go">${esc(t("go"))}</button>` : ""}
      <button class="ghost" data-act="reject">${esc(t("reject"))}</button><span class="sp"></span>
      <button class="ghost" data-act="answer">${esc(t("answer"))}</button></div>`;
  } else if (n.status === "done" || n.status === "working") {
    acts = `<details><summary class="toggle">${esc(t("follow"))}</summary><textarea rows="2" class="ans"></textarea>
      <div class="row"><span class="sp"></span><button class="ghost" data-act="answer">${esc(t("answer"))}</button></div></details>`;
  }
  const thread = (n.thread || []).map((m) => `<div><b>${esc(m.who === "agent" ? t("agent") : t("you"))}:</b> ${esc(m.text)}</div>`).join("");
  return `<div class="card" data-nid="${esc(n.id)}">
    <div class="head"><span class="cid">${esc(who)}</span>${kind ? `<span class="badge">${esc(kind)}</span>` : ""}
      ${n.comment ? `<span class="badge">${esc(n.comment)}</span>` : ""}<span class="sp"></span>
      ${n.block ? `<button class="locate" data-act="locate" data-b="${esc(n.block)}">${esc(where || t("locate"))}</button>` : ""}
      <span class="pill ${n.status}">${esc(n.status)}</span></div>
    ${n.title && n.author === "agent" ? `<div class="txt"><b>${esc(n.title)}</b></div>` : ""}
    ${n.quote ? `<div class="quote">${esc(n.quote)}</div>` : ""}
    ${thread ? `<div class="thread">${thread}</div>` : ""}
    <div class="txt">${esc(n.text)}</div>
    ${n.reply ? `<div class="reply"><b>${esc(n.title || t("agent"))}</b>${esc(n.reply)}</div>` : ""}
    ${acts}</div>`;
}

const timers = {};
$("#panel").addEventListener("input", (e) => {
  const f = e.target.dataset.field, card = e.target.closest(".card");
  if (!f || !card) return;
  const cid = card.dataset.cid, key = cid + f;
  clearTimeout(timers[key]);
  timers[key] = setTimeout(async () => {
    await api("api/comment", { id: cid, [f]: e.target.value });
    const sv = $(".saved", card);
    if (sv) { sv.classList.add("show"); setTimeout(() => sv.classList.remove("show"), 900); }
  }, 600);
});
$("#panel").addEventListener("focusout", () => setTimeout(() => { if (pending && !editing()) { pending = false; renderPanel(); } }, 50));

$("#panel").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) {
    const card = e.target.closest(".card[data-cid]");
    if (card && !e.target.closest("textarea,input,button")) { focus = card.dataset.cid; markOn(focus); $$(".card.focus").forEach((c) => c.classList.remove("focus")); card.classList.add("focus"); }
    return;
  }
  const card = b.closest(".card"), cid = card.dataset.cid, nid = card.dataset.nid, act = b.dataset.act;
  try {
    if (act === "open") { opened.add(cid); focus = cid; markOn(cid); renderPanel(); return; }
    if (act === "locate") { locate(b.dataset.b || cid); if (cid) markOn(cid); return; }
    if (act === "status") await api("api/comment", { id: cid, status: b.dataset.v });
    if (act === "root") {
      const c = S.comments.find((x) => x.id === cid);
      await api("api/comment", { id: cid, root_cause: c.root_cause === b.dataset.v ? null : b.dataset.v });
    }
    if (act === "ask") {
      const ta = $(".ask", card), text = ta.value.trim();
      if (!text) return ta.focus();
      const c = S.comments.find((x) => x.id === cid);
      await api("api/notes", { text, comment: cid, block: c.blocks[0] || null });
      ta.value = ""; toast(t("sent"));
    }
    if (act === "go") await api("api/answer", { id: nid, text: ($(".ans", card).value.trim() || t("go")) });
    if (act === "reject") await api("api/dismiss", { id: nid });
    if (act === "answer") {
      const ta = $(".ans", card);
      if (!ta.value.trim()) return ta.focus();
      await api("api/answer", { id: nid, text: ta.value.trim() });
    }
  } catch (err) { toast(err.message); }
  await refresh();
});

/* ------------------------------------------------------------ select text -> note */

let selInfo = null;
document.addEventListener("mouseup", (e) => {
  if (e.target.closest("#pop, #selbtn")) return;
  setTimeout(() => {
    const sel = window.getSelection(), text = String(sel).trim();
    const btn = $("#selbtn");
    if (!text || !sel.rangeCount || !$("#paper").contains(sel.anchorNode)) { btn.hidden = true; return; }
    const blk = (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement).closest(".blk");
    const mark = (sel.anchorNode.parentElement || sel.anchorNode).closest("mark.rd-mark");
    const r = sel.getRangeAt(0).getBoundingClientRect();
    selInfo = { quote: text.slice(0, 2000), block: blk ? blk.id : null,
                comment: mark ? mark.dataset.cid : (blk && blk.dataset.cids ? blk.dataset.cids.split(" ")[0] : null) };
    btn.textContent = "✎ " + t("note_btn");
    btn.style.left = (r.right + window.scrollX - 40) + "px";
    btn.style.top = (r.bottom + window.scrollY + 6) + "px";
    btn.hidden = false;
  }, 10);
});

$("#selbtn").addEventListener("click", () => {
  const pop = $("#pop"), btn = $("#selbtn");
  $(".pop-quote", pop).textContent = selInfo.quote;
  const opts = [`<option value="">${esc(t("general"))}</option>`].concat(
    S.comments.map((c) => `<option value="${esc(c.id)}"${c.id === selInfo.comment ? " selected" : ""}>${esc(c.id)} · ${esc(c.text.slice(0, 50))}</option>`));
  $(".pop-ref", pop).innerHTML = opts.join("");
  $(".pop-cancel", pop).textContent = t("cancel");
  $(".pop-send", pop).textContent = t("send");
  $("textarea", pop).placeholder = t("note_ph");
  pop.style.left = Math.max(8, Math.min(parseInt(btn.style.left) - 200, window.innerWidth - 400)) + "px";
  pop.style.top = btn.style.top;
  pop.hidden = false; btn.hidden = true;
  $("textarea", pop).focus();
});
$(".pop-cancel").addEventListener("click", () => { $("#pop").hidden = true; });
$(".pop-send").addEventListener("click", async () => {
  const pop = $("#pop"), ta = $("textarea", pop);
  if (!ta.value.trim()) return ta.focus();
  try {
    await api("api/notes", { text: ta.value.trim(), quote: selInfo.quote, block: selInfo.block,
                             comment: $(".pop-ref", pop).value || null });
    ta.value = ""; pop.hidden = true; toast(t("sent"));
    await refresh();
  } catch (err) { toast(err.message); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { $("#pop").hidden = true; $("#selbtn").hidden = true; }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !$("#pop").hidden) $(".pop-send").click();
});

refresh().then(() => {
  const h = new URLSearchParams(location.hash.slice(1));      // #tab=notes&c=R1.2 (links, screenshots)
  if (h.get("tab")) tab = h.get("tab");
  if (h.get("c")) focusComment(h.get("c")); else renderPanel();
  renderTop();
});
setInterval(refresh, 2000);
