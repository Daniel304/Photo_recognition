/* Photo Recognition — frontend SPA */
(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const apiKey = localStorage.getItem("apiKey") || "";
  async function api(path, opts = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    if (apiKey) headers["X-API-Key"] = apiKey;
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status}: ${text}`);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res.text();
  }

  // -------- Tabs --------
  const TABS = ["library", "people", "review", "search", "admin"];
  function showTab(name) {
    TABS.forEach(t => {
      $(`#view-${t}`).classList.toggle("hidden", t !== name);
      $(`.tab[data-tab="${t}"]`)?.classList.toggle("active", t === name);
    });
    if (name === "library") loadLibrary();
    if (name === "people") loadPeople();
    if (name === "review") loadReview();
    if (name === "admin") loadAdmin();
  }
  $$(".tab").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));

  // -------- Status pill --------
  async function pollStatus() {
    try {
      const s = await api("/api/admin/status");
      const pill = $("#status-pill");
      pill.classList.remove("scanning", "error");
      if (s.status === "scanning") {
        pill.classList.add("scanning");
        const pct = s.files_total ? Math.floor(100 * s.files_done / s.files_total) : 0;
        pill.textContent = `scanning ${s.files_done}/${s.files_total} (${pct}%)`;
      } else if (s.status === "error") {
        pill.classList.add("error");
        pill.textContent = "error";
      } else {
        pill.textContent = `idle · ${s.photo_count} photos · ${s.face_count} faces`;
      }
      $("#review-badge").textContent = s.pending_suggestions > 0 ? s.pending_suggestions : "";
      return s;
    } catch (e) {
      $("#status-pill").textContent = "offline";
      return null;
    }
  }
  pollStatus();
  setInterval(pollStatus, 3000);

  // -------- Library --------
  const lib = { offset: 0, limit: 60, q: "", order: "taken_desc", total: 0 };
  async function loadLibrary() {
    const params = new URLSearchParams({
      limit: lib.limit, offset: lib.offset, order: lib.order,
    });
    if (lib.q) params.set("q", lib.q);
    const data = await api(`/api/photos?${params}`);
    lib.total = data.total;
    const grid = $("#lib-grid");
    grid.innerHTML = "";
    for (const p of data.items) {
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.innerHTML = `
        <img loading="lazy" src="/api/photos/${p.id}/thumb" alt="">
        ${p.face_count ? `<div class="face-count">${p.face_count}&#9787;</div>` : ""}
        <div class="tile-info">${escapeHtml(p.filename)}${p.taken_at ? " · " + p.taken_at.slice(0,10) : ""}</div>`;
      tile.addEventListener("click", () => openLightbox(p.id));
      grid.appendChild(tile);
    }
    const start = lib.total ? lib.offset + 1 : 0;
    const end = Math.min(lib.offset + lib.limit, lib.total);
    $("#lib-count").textContent = `${start}–${end} of ${lib.total}`;
    $("#lib-page").textContent = `${start}–${end}`;
    $("#lib-prev").disabled = lib.offset === 0;
    $("#lib-next").disabled = end >= lib.total;
  }
  $("#lib-prev").addEventListener("click", () => { lib.offset = Math.max(0, lib.offset - lib.limit); loadLibrary(); });
  $("#lib-next").addEventListener("click", () => { lib.offset += lib.limit; loadLibrary(); });
  $("#lib-search").addEventListener("input", debounce(e => { lib.q = e.target.value; lib.offset = 0; loadLibrary(); }, 300));
  $("#lib-order").addEventListener("change", e => { lib.order = e.target.value; lib.offset = 0; loadLibrary(); });

  // -------- Lightbox --------
  async function openLightbox(photoId) {
    const data = await api(`/api/photos/${photoId}`);
    $("#lightbox-title").textContent = data.path;
    $("#lightbox-meta").innerHTML = [
      data.width && data.height ? `${data.width}×${data.height}` : null,
      data.taken_at ? `taken ${data.taken_at.replace("T", " ").slice(0,16)}` : null,
    ].filter(Boolean).join(" · ");
    const img = $("#lightbox-img");
    img.onload = () => placeBoxes(img, data);
    img.src = `/api/photos/${photoId}/original`;

    const facesEl = $("#lightbox-faces");
    facesEl.innerHTML = "";
    for (const f of data.faces) {
      facesEl.appendChild(faceTile(f));
    }
    $("#lightbox").classList.remove("hidden");
  }
  function placeBoxes(img, data) {
    const wrap = $("#lightbox-boxes");
    wrap.innerHTML = "";
    if (!data.width || !data.height) return;
    const rect = img.getBoundingClientRect();
    const parentRect = img.parentElement.getBoundingClientRect();
    const offsetX = rect.left - parentRect.left;
    const offsetY = rect.top - parentRect.top;
    const sx = rect.width / data.width;
    const sy = rect.height / data.height;
    for (const f of data.faces) {
      if (f.hidden) continue;
      const [x, y, w, h] = f.bbox;
      const div = document.createElement("div");
      div.className = "face-box" + (f.person_id ? "" : " unnamed");
      div.style.left = (offsetX + x * sx) + "px";
      div.style.top = (offsetY + y * sy) + "px";
      div.style.width = (w * sx) + "px";
      div.style.height = (h * sy) + "px";
      div.innerHTML = `<span class="lbl">${escapeHtml(f.person_name || "Unknown")}</span>`;
      div.addEventListener("click", e => { e.stopPropagation(); openAssign(f.id); });
      wrap.appendChild(div);
    }
  }
  $("#lightbox-close").addEventListener("click", () => $("#lightbox").classList.add("hidden"));
  $("#lightbox").addEventListener("click", e => { if (e.target === e.currentTarget) $("#lightbox").classList.add("hidden"); });

  function faceTile(f) {
    const t = document.createElement("div");
    t.className = "face-tile";
    t.innerHTML = `
      <img src="/api/faces/${f.id}/thumb" alt="">
      <div class="lbl ${f.person_id && !f.confirmed ? "unconfirmed" : ""}">${escapeHtml(f.person_name || "Unknown")}${f.person_id && !f.confirmed ? " ?" : ""}</div>`;
    t.addEventListener("click", () => openAssign(f.id));
    return t;
  }

  // -------- Assign modal --------
  let assignFaceId = null;
  let peopleCache = [];
  async function openAssign(faceId) {
    assignFaceId = faceId;
    $("#assign-face-img").src = `/api/faces/${faceId}/thumb`;
    $("#assign-new-name").value = "";
    peopleCache = await api("/api/people");
    const list = $("#assign-people-list");
    list.innerHTML = "";
    for (const p of peopleCache) {
      const chip = document.createElement("div");
      chip.className = "chip";
      chip.textContent = `${p.name} (${p.face_count})`;
      chip.addEventListener("click", () => assignTo({ person_id: p.id }));
      list.appendChild(chip);
    }
    $("#assign-modal").classList.remove("hidden");
  }
  $("#assign-confirm").addEventListener("click", () => {
    const name = $("#assign-new-name").value.trim();
    if (!name) return;
    assignTo({ person_name: name });
  });
  $("#assign-cancel").addEventListener("click", () => $("#assign-modal").classList.add("hidden"));
  $("#assign-hide").addEventListener("click", async () => {
    if (!assignFaceId) return;
    await api(`/api/faces/${assignFaceId}/hide`, { method: "POST" });
    $("#assign-modal").classList.add("hidden");
    pollStatus();
  });
  async function assignTo(body) {
    if (!assignFaceId) return;
    const res = await api(`/api/faces/${assignFaceId}/assign`, {
      method: "POST",
      body: JSON.stringify(Object.assign({ confirmed: true }, body)),
    });
    $("#assign-modal").classList.add("hidden");
    pollStatus();
    if (res.new_suggestions > 0) {
      toast(`Found ${res.new_suggestions} possible matches — head to Review.`);
    }
  }

  // -------- People --------
  async function loadPeople() {
    $("#person-detail").classList.add("hidden");
    $("#people-grid").classList.remove("hidden");
    const list = await api("/api/people");
    $("#people-count").textContent = `${list.length} people`;
    const grid = $("#people-grid");
    grid.innerHTML = "";
    if (!list.length) {
      grid.innerHTML = `<p class="muted">No named people yet. Click any face on the Library tab and give it a name.</p>`;
    }
    for (const p of list) {
      const card = document.createElement("div");
      card.className = "person-card";
      const cover = p.cover_face_id ? `/api/faces/${p.cover_face_id}/thumb` : null;
      card.innerHTML = `
        ${cover ? `<img class="cover" src="${cover}">` : `<div class="cover"></div>`}
        <div class="name">${escapeHtml(p.name)}</div>
        <div class="stats">${p.face_count} faces · ${p.confirmed_count} confirmed</div>`;
      card.addEventListener("click", () => openPerson(p.id));
      grid.appendChild(card);
    }
  }
  $("#new-person-btn").addEventListener("click", async () => {
    const name = $("#new-person-name").value.trim();
    if (!name) return;
    await api("/api/people", { method: "POST", body: JSON.stringify({ name }) });
    $("#new-person-name").value = "";
    loadPeople();
  });

  async function openPerson(id) {
    const p = await api(`/api/people/${id}`);
    $("#people-grid").classList.add("hidden");
    $("#person-detail").classList.remove("hidden");
    $("#person-name").textContent = p.name;
    $("#person-detail").dataset.personId = id;

    const faces = await api(`/api/faces?person_id=${id}&limit=200`);
    const faceEl = $("#person-faces");
    faceEl.innerHTML = "";
    for (const f of faces.items) faceEl.appendChild(faceTile({ ...f, person_name: p.name }));

    const photos = await api(`/api/photos?person_id=${id}&limit=120`);
    const photoEl = $("#person-photos");
    photoEl.innerHTML = "";
    for (const ph of photos.items) {
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.innerHTML = `<img loading="lazy" src="/api/photos/${ph.id}/thumb">
        <div class="tile-info">${escapeHtml(ph.filename)}</div>`;
      tile.addEventListener("click", () => openLightbox(ph.id));
      photoEl.appendChild(tile);
    }
  }
  $("#back-to-people").addEventListener("click", loadPeople);
  $("#person-rename").addEventListener("click", async () => {
    const id = $("#person-detail").dataset.personId;
    const newName = prompt("New name", $("#person-name").textContent);
    if (!newName) return;
    await api(`/api/people/${id}`, { method: "PATCH", body: JSON.stringify({ name: newName.trim() }) });
    openPerson(id);
  });
  $("#person-rescan").addEventListener("click", async () => {
    const id = $("#person-detail").dataset.personId;
    const r = await api(`/api/people/${id}/rescan-suggestions`, { method: "POST" });
    toast(`Queued ${r.added} new candidate faces for review.`);
    pollStatus();
  });
  $("#person-delete").addEventListener("click", async () => {
    const id = $("#person-detail").dataset.personId;
    if (!confirm("Delete this person? Their faces will become unassigned.")) return;
    await api(`/api/people/${id}`, { method: "DELETE" });
    loadPeople();
  });

  // -------- Review (swipe) --------
  let queue = [];
  let activeCard = null;

  async function loadReview() {
    const stage = $("#swipe-stage");
    stage.innerHTML = '<div id="swipe-empty" class="empty hidden"></div>';
    queue = await api("/api/review/suggestions?limit=50");
    $("#review-remaining").textContent = `${queue.length} pending`;
    if (!queue.length) {
      $("#swipe-empty").classList.remove("hidden");
      $("#swipe-empty").textContent = "Nothing to review right now. Name a few faces to seed the matcher.";
      return;
    }
    renderTopCard();
  }
  function renderTopCard() {
    const stage = $("#swipe-stage");
    stage.querySelectorAll(".swipe-card").forEach(el => el.remove());
    if (!queue.length) {
      $("#review-remaining").textContent = "0 pending";
      $("#swipe-empty")?.classList.remove("hidden");
      return;
    }
    $("#swipe-empty")?.classList.add("hidden");

    // Render up to 2 stacked
    for (let i = Math.min(queue.length, 2) - 1; i >= 0; i--) {
      const s = queue[i];
      const card = document.createElement("div");
      card.className = "swipe-card";
      card.style.zIndex = String(10 - i);
      card.style.transform = i === 0 ? "" : `translateY(${i * 8}px) scale(${1 - i * 0.03})`;
      card.style.opacity = i === 0 ? "1" : "0.6";
      card.innerHTML = `
        <div class="top">
          <img class="face-img" src="/api/faces/${s.face_id}/thumb">
          <img class="source-thumb" src="/api/photos/${s.photo_id}/thumb" title="Source photo">
          <div class="stamp accept">YES</div>
          <div class="stamp reject">NO</div>
        </div>
        <div class="bottom">
          <div class="question">Is this</div>
          <div class="name">${escapeHtml(s.person_name)}?</div>
          <div class="score">match ${(s.score * 100).toFixed(1)}%</div>
        </div>`;
      stage.appendChild(card);
      if (i === 0) {
        activeCard = card;
        attachSwipe(card, s);
      }
    }
    $("#review-remaining").textContent = `${queue.length} pending`;
  }
  function attachSwipe(card, suggestion) {
    let startX = 0, startY = 0, dx = 0, dy = 0, dragging = false;
    const onDown = (e) => {
      dragging = true;
      const p = pt(e);
      startX = p.x; startY = p.y;
      card.style.transition = "none";
    };
    const onMove = (e) => {
      if (!dragging) return;
      const p = pt(e);
      dx = p.x - startX; dy = p.y - startY;
      const rot = dx / 20;
      card.style.transform = `translate(${dx}px, ${dy}px) rotate(${rot}deg)`;
      card.querySelector(".stamp.accept").style.opacity = dx > 30 ? Math.min(1, dx / 120) : 0;
      card.querySelector(".stamp.reject").style.opacity = dx < -30 ? Math.min(1, -dx / 120) : 0;
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      card.style.transition = "";
      if (dx > 110) finishSwipe(card, suggestion, "accept");
      else if (dx < -110) finishSwipe(card, suggestion, "reject");
      else card.style.transform = "";
    };
    card.addEventListener("mousedown", onDown);
    card.addEventListener("touchstart", onDown, { passive: true });
    window.addEventListener("mousemove", onMove);
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchend", onUp);

    card._cleanup = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchend", onUp);
    };
  }
  function pt(e) {
    if (e.touches && e.touches[0]) return { x: e.touches[0].clientX, y: e.touches[0].clientY };
    return { x: e.clientX, y: e.clientY };
  }
  async function finishSwipe(card, suggestion, action) {
    card._cleanup?.();
    const dir = action === "accept" ? 1 : -1;
    card.style.transition = "transform 250ms ease, opacity 250ms";
    card.style.transform = `translate(${dir * window.innerWidth}px, 60px) rotate(${dir * 30}deg)`;
    card.style.opacity = "0";
    queue.shift();
    try {
      if (action === "accept") {
        await api(`/api/review/suggestions/${suggestion.id}/accept`, { method: "POST" });
      } else {
        await api(`/api/review/suggestions/${suggestion.id}/reject`, { method: "POST" });
      }
    } catch (e) {
      toast("Error: " + e.message);
    }
    setTimeout(() => { card.remove(); renderTopCard(); pollStatus(); }, 220);
  }
  async function skipTop() {
    if (!queue.length) return;
    const s = queue[0];
    queue.shift();
    try { await api(`/api/review/suggestions/${s.id}/skip`, { method: "POST" }); } catch {}
    renderTopCard();
  }
  $("#swipe-accept").addEventListener("click", () => { if (activeCard && queue[0]) finishSwipe(activeCard, queue[0], "accept"); });
  $("#swipe-reject").addEventListener("click", () => { if (activeCard && queue[0]) finishSwipe(activeCard, queue[0], "reject"); });
  $("#swipe-skip").addEventListener("click", skipTop);
  window.addEventListener("keydown", e => {
    if ($("#view-review").classList.contains("hidden")) return;
    if (e.key === "ArrowRight" && activeCard && queue[0]) finishSwipe(activeCard, queue[0], "accept");
    else if (e.key === "ArrowLeft" && activeCard && queue[0]) finishSwipe(activeCard, queue[0], "reject");
    else if (e.key === " ") { e.preventDefault(); skipTop(); }
  });

  // -------- Search & clustering --------
  $("#search-go").addEventListener("click", doSearch);
  $("#search-q").addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });
  async function doSearch() {
    const q = $("#search-q").value.trim();
    const data = await api(`/api/photos?q=${encodeURIComponent(q)}&limit=80`);
    const grid = $("#search-results");
    grid.innerHTML = "";
    for (const p of data.items) {
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.innerHTML = `<img loading="lazy" src="/api/photos/${p.id}/thumb">
        <div class="tile-info">${escapeHtml(p.filename)}</div>`;
      tile.addEventListener("click", () => openLightbox(p.id));
      grid.appendChild(tile);
    }
  }
  $("#cluster-btn").addEventListener("click", async () => {
    const out = $("#clusters");
    out.innerHTML = "Clustering...";
    try {
      const clusters = await api("/api/search/cluster-unassigned", { method: "POST" });
      out.innerHTML = "";
      if (!clusters.length) {
        out.innerHTML = "<p class='muted'>No clusters found.</p>";
        return;
      }
      for (const c of clusters) {
        const card = document.createElement("div");
        card.className = "cluster";
        card.innerHTML = `
          <div class="cluster-head">
            <strong>${c.size} similar faces</strong>
            <input placeholder="Name this person..." class="cluster-name">
            <button class="cluster-name-btn">Name all</button>
          </div>
          <div class="cluster-faces"></div>`;
        const facesEl = card.querySelector(".cluster-faces");
        for (const fid of c.face_ids.slice(0, 24)) {
          const img = document.createElement("img");
          img.src = `/api/faces/${fid}/thumb`;
          img.title = `face ${fid}`;
          img.addEventListener("click", () => openAssign(fid));
          facesEl.appendChild(img);
        }
        card.querySelector(".cluster-name-btn").addEventListener("click", async () => {
          const name = card.querySelector(".cluster-name").value.trim();
          if (!name) return;
          for (const fid of c.face_ids) {
            try {
              await api(`/api/faces/${fid}/assign`, {
                method: "POST",
                body: JSON.stringify({ person_name: name, confirmed: true }),
              });
            } catch (e) { console.warn(e); }
          }
          toast(`Assigned ${c.face_ids.length} faces to "${name}"`);
          pollStatus();
        });
        out.appendChild(card);
      }
    } catch (e) {
      out.innerHTML = `<p class="muted">${escapeHtml(e.message)}</p>`;
    }
  });

  // -------- Admin --------
  async function loadAdmin() {
    const s = await api("/api/admin/status");
    const stats = $("#admin-stats");
    stats.innerHTML = "";
    const cards = [
      ["Photos indexed", s.photo_count],
      ["Faces detected", s.face_count],
      ["Named people", s.person_count],
      ["Unassigned faces", s.unassigned_face_count],
      ["Pending review", s.pending_suggestions],
      ["Scan progress", s.files_total ? `${s.files_done}/${s.files_total}` : "—"],
    ];
    for (const [lbl, num] of cards) {
      const div = document.createElement("div");
      div.className = "stat";
      div.innerHTML = `<div class="num">${num}</div><div class="lbl">${lbl}</div>`;
      stats.appendChild(div);
    }
    $("#admin-root").textContent = "PHOTO_ROOT (configured in docker-compose.yml)";
  }
  $("#scan-btn").addEventListener("click", async () => {
    try { await api("/api/admin/scan", { method: "POST" }); toast("Scan started"); }
    catch (e) { toast(e.message); }
    setTimeout(loadAdmin, 500);
  });
  $("#scan-cancel-btn").addEventListener("click", async () => {
    await api("/api/admin/scan/cancel", { method: "POST" });
    toast("Cancellation requested");
  });

  // -------- Utils --------
  function escapeHtml(s) {
    return (s ?? "").toString().replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }
  let toastTimer;
  function toast(msg) {
    let el = $("#toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.style.cssText = "position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#000;color:#fff;padding:10px 16px;border-radius:8px;z-index:200;box-shadow:0 4px 16px rgba(0,0,0,0.4);";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.opacity = "1";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.style.transition = "opacity 400ms"; el.style.opacity = "0"; }, 2200);
  }

  // boot
  showTab("library");
})();
