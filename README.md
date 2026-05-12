# Photo Recognition

A self-hosted, web-based photo indexer with face recognition, built for running
in a Docker container on a Synology NAS (or anywhere else).

**Originals are never moved, renamed, or modified.** The app only reads from
your photo folder and writes its own thumbnails, face crops, and a SQLite
database to a separate `data/` volume.

## Features

- Recursive indexing of a configured photo folder (read-only mount).
- Face detection + 512-d embeddings via [InsightFace](https://github.com/deepinsight/insightface)
  (small CPU model, ONNX runtime — no GPU required).
- Auto-assignment of faces to a named person when the cosine similarity is
  above a strict threshold; "swipe left / swipe right" review queue for
  medium-confidence matches.
- Picasa-style People view, manual naming, rename, merge, delete.
- Find similar faces and DBSCAN clustering of unknown faces so you can name a
  whole group at once.
- **Albums and Tags** (many-to-many) — put one photo in "Vacation 2024" *and*
  "kids" *and* "favorites" all at once. Cover photo auto-set.
- **Favorites and 0–5 star ratings** with library filters.
- **GPS extraction** from EXIF, with a per-event OpenStreetMap (Leaflet) map.
- **Auto-detected events** — date+place clustering (Picasa-style "trip
  detected"). Renames are sticky across rebuilds.
- **Near-duplicate detection** via 64-bit perceptual hash. Surfaces the
  highest-resolution candidate per group; files are never deleted server-side.
- Library browser with EXIF date sorting, filename search, favorite & rating filters.
- Periodic re-scan picks up new files and marks deleted ones as missing.

## Is face recognition "sensible/needed" here?

Yes — that's the only reliable way to get Picasa-style grouping. The pipeline is:
1. Detect faces in each photo.
2. Compute a 512-d embedding per face.
3. Compare embeddings via cosine similarity to confirmed faces of known people.
4. Above `AUTO_MATCH_THRESHOLD` (0.62 default): auto-tag.
   Between `SUGGEST_THRESHOLD` (0.45) and the auto threshold: queue for swipe review.
   Below that: leave as unknown for clustering / manual naming.

The model files are downloaded once on first launch into `/data/models` and cached.

## Synology setup

1. SSH into your NAS (or use Container Manager → Project).
2. Clone or copy this folder to e.g. `/volume1/docker/photo-recognition`.
3. Edit `docker-compose.yml`:
   - Change the `/volume1/photo:/photos:ro` line to point at the share you want
     indexed (the `:ro` keeps it read-only — recommended).
4. Build & start:
   ```bash
   sudo docker compose up -d --build
   ```
5. Open `http://<nas-ip>:8000` in a browser.

On first launch the indexer will start automatically. Watch the status pill in
the top-right for progress.

### Volumes

| Container path | Purpose                                       |
|----------------|-----------------------------------------------|
| `/photos`      | Your photo library (mount **read-only**).     |
| `/data`        | SQLite DB, thumbnails, face crops, ML models. |

### Environment variables (set in `docker-compose.yml`)

| Variable | Default | Notes |
|----------|---------|-------|
| `PHOTO_ROOT` | `/photos` | Indexed recursively. |
| `DATA_DIR` | `/data` | Persistent state. |
| `AUTO_MATCH_THRESHOLD` | `0.62` | Lower = more aggressive auto-tagging. |
| `SUGGEST_THRESHOLD` | `0.45` | Lower = more swipe suggestions. |
| `ALLOWED_EXTENSIONS` | `.jpg,.jpeg,.png,.heic,.heif,.webp,.bmp,.tif,.tiff` | |
| `SCAN_INTERVAL` | `3600` | Re-scan period in seconds. `0` = manual only. |
| `FACE_MODEL` | `buffalo_sc` | Try `buffalo_l` for better accuracy if you have CPU headroom. |
| `API_KEY` | (empty) | If set, all `/api/*` calls must send `X-API-Key`. |

## Using the app

- **Library**: browse all indexed photos. Click a photo to open it with face
  boxes overlaid. Click a face box to name it. In the lightbox you can
  favorite, star-rate (`F`, `0`–`5`), and add the photo to any albums/tags.
- **People**: see everyone you've named, drill in to see all their photos,
  rename, merge with another person, or trigger "find more faces" to search
  unassigned faces for matches.
- **Albums**: top section lists named albums (Vacation 2024, etc.). Bottom
  section lists tags (`#kids`, `#christmas`). A photo can be in any number
  of either.
- **Events**: auto-clustered trips/days. Click "Rebuild events" to recompute
  from EXIF date+GPS. Renames are remembered across rebuilds. Events with
  GPS show a Leaflet map of where each photo was taken.
- **Review**: the swipe queue. The AI shows you a face and asks
  "Is this <Name>?" — swipe right (or `→`) to accept, left (or `←`) to reject,
  space to skip. Use it after you've named ~5–10 faces for a person.
- **Search**: filename/folder search, "Cluster unassigned faces" to group
  unknown faces with DBSCAN, and "Find near-duplicates" via perceptual hash.
- **Admin**: stats and manual scan controls.

## Architecture

```
app/
├── main.py            FastAPI entry, lifespan, static mounts
├── config.py          Settings (env-driven)
├── database.py        SQLite + SQLAlchemy
├── models.py          Photo, Person, Face, Suggestion, ScanState
├── schemas.py         Pydantic
├── face_engine.py     InsightFace wrapper (singleton)
├── image_utils.py     Pillow load, EXIF, thumb/face crop helpers
├── matcher.py         Cosine matching, auto-assign vs. suggest logic
├── clustering.py      DBSCAN over unassigned embeddings
├── indexer.py         Background scanner thread
├── api/               FastAPI routers (photos, faces, people, review, search, admin)
└── web/               Vanilla-JS SPA (index.html, app.js, style.css)
```

## API

All endpoints live under `/api`. Browse interactive docs at
`http://<nas-ip>:8000/docs` once the container is up.

## License

MIT
