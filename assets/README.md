# Assets

Imágenes estáticas usadas por el generador de PDF (`dashboard/pdf_report.py`).

## Archivos esperados

- `club_dlp_logo.png` — logo del Club DLP que aparece en la página 3 del PDF (CTA / lead magnet).
  - **Formato**: PNG con fondo transparente recomendado (también acepta JPG).
  - **Tamaño**: ≥ 600px de alto para que se vea nítido al escalar.
  - Si el archivo no existe, el generador usa un fallback textual estilizado en lugar de crashear.

## Fuentes (opcional)

- `fonts/JetBrainsMono-Bold.ttf`, `fonts/JetBrainsMono-Regular.ttf`, `fonts/Inter-Regular.ttf`, `fonts/Inter-Bold.ttf`
  - Si están presentes, el PDF usa estas fuentes (fidelidad total con la app).
  - Si NO están, el PDF cae a Helvetica/Courier built-in de reportlab (legible, menos sexy).
