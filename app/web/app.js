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
  const TABS = ["library", "people", "albums", "events", "review", "search", "admin"];
  function showTab(name) {
    TABS.forEach(t => {
      $(`#view-${t}`).classList.toggle("hidden", t !== name);
      $(`.tab[data-tab="${t}"]`)?.classList.toggle("active", t === name);
    });
    if (name === "library") loadLibrary();
    if (name === "people") loadPeople();
    if (name === "albums") loadAlbums();
    if (name === "events") loadEvents();
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
  const lib = { offset: 0, limit: 60, q: "", order: "taken_desc", total: 0, favorite: false, min_rating: "" };
  async function loadLibrary() {
    const params = new URLSearchParams({
      limit: lib.limit, offset: lib.offset, order: lib.order,
    });
    if (lib.q) params.set("q", lib.q);
    if (lib.favorite) params.set("favorite", "true");
    if (lib.min_rating) params.set("min_rating", lib.min_rating);
    const data = await api(`/api/photos?${params}`);
    lib.total = data.total;
    const grid = $("#lib-grid");
    grid.innerHTML = "";
    for (const p of data.items) {
      grid.appendChild(photoTile(p));
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
  $("#lib-fav").addEventListener("change", e => { lib.favorite = e.target.checked; lib.offset = 0; loadLibrary(); });
  $("#lib-rating").addEventListener("change", e => { lib.min_rating = e.target.value; lib.offset = 0; loadLibrary(); });

  function photoTile(p) {
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.innerHTML = `
      <img loading="lazy" src="/api/photos/${p.id}/thumb" alt="">
      ${p.face_count ? `<div class="face-count">${p.face_count}&#9787;</div>` : ""}
      ${p.favorite ? `<div class="fav-marker" title="Favorite">&#9829;</div>` : ""}
      ${p.rating ? `<div class="rating-marker">${p.rating}&#9733;</div>` : ""}
      <div class="tile-info">${escapeHtml(p.filename || "")}${p.taken_at ? " · " + p.taken_at.slice(0,10) : ""}</div>`;
    tile.addEventListener("click", () => openLightbox(p.id));
    return tile;
  }

  // -------- Lightbox --------
  let lightboxPhotoId = null;
  async function openLightbox(photoId) {
    lightboxPhotoId = photoId;
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

    renderFavStar(data.favorite, data.rating);

    if (data.gps_lat != null && data.gps_lon != null) {
      $("#lightbox-gps").innerHTML =
        `${data.gps_lat.toFixed(5)}, ${data.gps_lon.toFixed(5)} · ` +
        `<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${data.gps_lat}&mlon=${data.gps_lon}&zoom=14">map &#8599;</a>`;
    } else {
      $("#lightbox-gps").textContent = "—";
    }

    refreshLightboxAlbums();
    $("#lightbox").classList.remove("hidden");
  }

  function renderFavStar(favorite, rating) {
    const fav = $("#lightbox-fav");
    fav.classList.toggle("on", !!favorite);
    fav.textContent = favorite ? "♥" : "♡";
    const stars = $("#lightbox-stars");
    stars.innerHTML = "";
    for (let i = 1; i <= 5; i++) {
      const s = document.createElement("span");
      s.className = "star" + (i <= (rating || 0) ? " on" : "");
      s.dataset.value = i;
      s.textContent = "★";
      stars.appendChild(s);
    }
  }
  $("#lightbox-fav").addEventListener("click", async () => {
    if (!lightboxPhotoId) return;
    const on = !$("#lightbox-fav").classList.contains("on");
    const r = await api(`/api/photos/${lightboxPhotoId}/favorite`, {
      method: "POST", body: JSON.stringify({ favorite: on }),
    });
    renderFavStar(r.favorite, currentRating());
  });
  $("#lightbox-stars").addEventListener("click", async e => {
    const v = e.target?.dataset?.value;
    if (!v || !lightboxPhotoId) return;
    const newVal = (currentRating() === parseInt(v, 10)) ? 0 : parseInt(v, 10);
    const r = await api(`/api/photos/${lightboxPhotoId}/rating`, {
      method: "POST", body: JSON.stringify({ rating: newVal }),
    });
    renderFavStar($("#lightbox-fav").classList.contains("on"), r.rating);
  });
  function currentRating() {
    return $$("#lightbox-stars .star.on").length;
  }

  async function refreshLightboxAlbums() {
    if (!lightboxPhotoId) return;
    const [albums, allAlbums] = await Promise.all([
      api(`/api/albums/photo/${lightboxPhotoId}`),
      api(`/api/albums`),
    ]);
    const wrap = $("#lightbox-albums");
    wrap.innerHTML = "";
    if (!albums.length) wrap.innerHTML = '<span class="muted">None yet.</span>';
    for (const a of albums) {
      const chip = document.createElement("span");
      chip.className = "chip " + (a.kind === "tag" ? "tag" : "");
      chip.innerHTML = `${escapeHtml(a.name)} <button title="Remove">&times;</button>`;
      chip.querySelector("button").addEventListener("click", async () => {
        await api(`/api/albums/${a.id}/photos/${lightboxPhotoId}`, { method: "DELETE" });
        refreshLightboxAlbums();
      });
      wrap.appendChild(chip);
    }
    const sel = $("#lightbox-album-select");
    const have = new Set(albums.map(a => a.id));
    sel.innerHTML = '<option value="">— add to album / tag —</option>';
    for (const a of allAlbums) {
      if (have.has(a.id)) continue;
      const opt = document.createElement("option");
      opt.value = a.id;
      opt.textContent = `${a.kind === "tag" ? "#" : ""}${a.name}`;
      sel.appendChild(opt);
    }
  }
  $("#lightbox-album-add").addEventListener("click", async () => {
    const sel = $("#lightbox-album-select");
    const aid = sel.value;
    if (!aid || !lightboxPhotoId) return;
    await api(`/api/albums/${aid}/photos`, {
      method: "POST", body: JSON.stringify({ photo_ids: [lightboxPhotoId] }),
    });
    refreshLightboxAlbums();
  });
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
    for (const ph of photos.items) photoEl.appendChild(photoTile(ph));
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
    for (const p of data.items) grid.appendChild(photoTile(p));
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

  // -------- Albums + Tags --------
  async function loadAlbums() {
    $("#album-detail").classList.add("hidden");
    $("#albums-grid").classList.remove("hidden");
    $("#tags-list").classList.remove("hidden");
    const list = await api("/api/albums");
    const albums = list.filter(a => a.kind === "album");
    const tags = list.filter(a => a.kind === "tag");
    const grid = $("#albums-grid");
    grid.innerHTML = "";
    if (!albums.length) {
      grid.innerHTML = '<p class="muted">No albums yet. Create one above or use "Add to album..." in the lightbox.</p>';
    }
    for (const a of albums) {
      const card = document.createElement("div");
      card.className = "person-card";
      const cover = a.cover_photo_id ? `/api/photos/${a.cover_photo_id}/thumb` : null;
      card.innerHTML = `
        ${cover ? `<img class="cover" src="${cover}">` : `<div class="cover"></div>`}
        <div class="name">${escapeHtml(a.name)}</div>
        <div class="stats">${a.photo_count} photos</div>`;
      card.addEventListener("click", () => openAlbum(a.id));
      grid.appendChild(card);
    }
    const tagsEl = $("#tags-list");
    tagsEl.innerHTML = "";
    if (!tags.length) {
      tagsEl.innerHTML = '<span class="muted">No tags yet.</span>';
    }
    for (const t of tags) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `#${escapeHtml(t.name)} <span class="count">${t.photo_count}</span>`;
      chip.addEventListener("click", () => openAlbum(t.id));
      tagsEl.appendChild(chip);
    }
  }
  $("#new-album-btn").addEventListener("click", async () => {
    const name = $("#new-album-name").value.trim();
    const kind = $("#new-album-kind").value;
    if (!name) return;
    try {
      await api("/api/albums", { method: "POST", body: JSON.stringify({ name, kind }) });
      $("#new-album-name").value = "";
      loadAlbums();
    } catch (e) { toast(e.message); }
  });
  async function openAlbum(id) {
    const a = await api(`/api/albums/${id}`);
    $("#albums-grid").classList.add("hidden");
    $("#tags-list").classList.add("hidden");
    $("#album-detail").classList.remove("hidden");
    $("#album-name").textContent = a.name;
    $("#album-kind-pill").textContent = a.kind;
    $("#album-detail").dataset.albumId = id;
    const photos = await api(`/api/photos?album_id=${id}&limit=200`);
    const grid = $("#album-photos");
    grid.innerHTML = "";
    if (!photos.items.length) grid.innerHTML = '<p class="muted">No photos in this album/tag yet.</p>';
    for (const p of photos.items) grid.appendChild(photoTile(p));
  }
  $("#back-to-albums").addEventListener("click", loadAlbums);
  $("#album-rename").addEventListener("click", async () => {
    const id = $("#album-detail").dataset.albumId;
    const newName = prompt("New name", $("#album-name").textContent);
    if (!newName) return;
    try {
      await api(`/api/albums/${id}`, { method: "PATCH", body: JSON.stringify({ name: newName.trim() }) });
      openAlbum(id);
    } catch (e) { toast(e.message); }
  });
  $("#album-delete").addEventListener("click", async () => {
    const id = $("#album-detail").dataset.albumId;
    if (!confirm("Delete this album/tag? (Photos are kept.)")) return;
    await api(`/api/albums/${id}`, { method: "DELETE" });
    loadAlbums();
  });

  // -------- Events --------
  async function loadEvents() {
    $("#event-detail").classList.add("hidden");
    $("#events-list").classList.remove("hidden");
    const list = await api("/api/events");
    const grid = $("#events-list");
    grid.innerHTML = "";
    if (!list.length) {
      grid.innerHTML = '<p class="muted">No events detected yet. Click "Rebuild events" to cluster photos by date and GPS.</p>';
      return;
    }
    for (const e of list) {
      const card = document.createElement("div");
      card.className = "event-card";
      const cover = e.cover_photo_id ? `/api/photos/${e.cover_photo_id}/thumb` : null;
      const start = e.start_at?.slice(0,10) || "?";
      const end = e.end_at?.slice(0,10) || start;
      const range = start === end ? start : `${start} → ${end}`;
      card.innerHTML = `
        ${cover ? `<img src="${cover}">` : `<div style="aspect-ratio:16/10;background:#222"></div>`}
        <div class="meta">
          <div class="name">${escapeHtml(e.name)}</div>
          <div class="sub">${e.photo_count} photos · ${range}${e.gps_lat != null ? " · 📍" : ""}</div>
        </div>`;
      card.addEventListener("click", () => openEvent(e.id));
      grid.appendChild(card);
    }
  }
  $("#events-rebuild").addEventListener("click", async () => {
    try {
      const r = await api("/api/events/rebuild", { method: "POST" });
      toast(`Detected ${r.events} events.`);
      loadEvents();
    } catch (e) { toast(e.message); }
  });
  async function openEvent(id) {
    const e = await api(`/api/events/${id}`);
    $("#events-list").classList.add("hidden");
    $("#event-detail").classList.remove("hidden");
    $("#event-detail").dataset.eventId = id;
    $("#event-name").textContent = e.name;
    const start = e.start_at?.replace("T", " ").slice(0,16);
    const end = e.end_at?.replace("T", " ").slice(0,16);
    $("#event-meta").textContent = `${start || ""} → ${end || ""} · ${e.photo_count} photos`;
    const mapEl = $("#event-map");
    mapEl.classList.add("hidden");
    mapEl.innerHTML = "";

    const photos = await api(`/api/photos?event_id=${id}&limit=500&order=taken_asc`);
    const grid = $("#event-photos");
    grid.innerHTML = "";
    for (const p of photos.items) grid.appendChild(photoTile(p));

    if (e.gps_lat != null && e.gps_lon != null) {
      mapEl.classList.remove("hidden");
      const gps = await api(`/api/events/${id}/gps`);
      await ensureLeaflet();
      const map = L.map(mapEl).setView([e.gps_lat, e.gps_lon], 11);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      const bounds = [];
      for (const g of gps) {
        const m = L.marker([g.lat, g.lon]).addTo(map);
        m.on("click", () => openLightbox(g.photo_id));
        bounds.push([g.lat, g.lon]);
      }
      if (bounds.length > 1) map.fitBounds(bounds, { padding: [24, 24] });
    }
  }
  $("#back-to-events").addEventListener("click", loadEvents);
  $("#event-rename").addEventListener("click", async () => {
    const id = $("#event-detail").dataset.eventId;
    const newName = prompt("New name", $("#event-name").textContent);
    if (!newName) return;
    await api(`/api/events/${id}`, { method: "PATCH", body: JSON.stringify({ name: newName.trim() }) });
    openEvent(id);
  });
  $("#event-delete").addEventListener("click", async () => {
    const id = $("#event-detail").dataset.eventId;
    if (!confirm("Delete this event? (Photos are kept.)")) return;
    await api(`/api/events/${id}`, { method: "DELETE" });
    loadEvents();
  });

  // Lazy-load Leaflet from CDN only when an event map is shown.
  let leafletPromise = null;
  function ensureLeaflet() {
    if (window.L) return Promise.resolve();
    if (leafletPromise) return leafletPromise;
    leafletPromise = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(css);
      const s = document.createElement("script");
      s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      s.onload = resolve;
      s.onerror = () => reject(new Error("Leaflet failed to load (no internet from NAS?)"));
      document.head.appendChild(s);
    });
    return leafletPromise;
  }

  // -------- Duplicates --------
  $("#dup-btn").addEventListener("click", async () => {
    const t = parseInt($("#dup-threshold").value, 10) || 8;
    const out = $("#duplicates");
    out.innerHTML = "Scanning... (this can take a few seconds for large libraries)";
    try {
      const r = await api(`/api/duplicates?threshold=${t}`);
      out.innerHTML = "";
      if (!r.groups.length) {
        out.innerHTML = "<p class='muted'>No near-duplicates found at that threshold.</p>";
        return;
      }
      out.innerHTML = `<p class="muted">${r.groups.length} group(s) found. The outlined photo is the highest-resolution candidate — files are never deleted automatically.</p>`;
      for (const g of r.groups) {
        const card = document.createElement("div");
        card.className = "dup-group";
        card.innerHTML = `<div class="dup-head">${g.size} similar photos</div><div class="dup-photos"></div>`;
        const photosEl = card.querySelector(".dup-photos");
        for (const pid of g.photo_ids) {
          const wrap = document.createElement("div");
          wrap.className = "dup-photo" + (pid === g.primary_photo_id ? " primary" : "");
          wrap.innerHTML = `<img src="/api/photos/${pid}/thumb" title="open">
            <div class="lbl">#${pid}${pid === g.primary_photo_id ? " · suggested keeper" : ""}</div>`;
          wrap.querySelector("img").addEventListener("click", () => openLightbox(pid));
          photosEl.appendChild(wrap);
        }
        out.appendChild(card);
      }
    } catch (e) {
      out.innerHTML = `<p class="muted">${escapeHtml(e.message)}</p>`;
    }
  });

  // Keyboard: F to favorite, 0–5 to rate (only when lightbox open)
  window.addEventListener("keydown", e => {
    if ($("#lightbox").classList.contains("hidden")) return;
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.key === "f" || e.key === "F") { $("#lightbox-fav").click(); }
    if (e.key >= "0" && e.key <= "5") {
      const star = $$("#lightbox-stars .star").find(s => s.dataset.value === e.key);
      if (e.key === "0") {
        // clear
        api(`/api/photos/${lightboxPhotoId}/rating`, { method: "POST", body: JSON.stringify({ rating: 0 }) })
          .then(() => renderFavStar($("#lightbox-fav").classList.contains("on"), 0));
      } else if (star) {
        star.click();
      }
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
