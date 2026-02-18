# Tonie Reference Images (Fotoerkennung v1)

Lege Referenzbilder hier ab, nach Tonie-ID gruppiert:

```text
app/data/tonie_refs/
  tn_001/
    front.jpg
    side.png
  tn_002/
    image1.jpg
```

Danach den Index bauen:

```bash
cd backend
python scripts/build_photo_reference_index.py
```

Der Builder schreibt:

- `app/data/tonie_reference_index.json`

API-Status prüfen:

- `GET /api/tonies/recognize-status`

Bild erkennen (multipart/form-data):

- `POST /api/tonies/recognize`
  - Form field: `image`
  - Optional Query: `top_k` (1..5)
