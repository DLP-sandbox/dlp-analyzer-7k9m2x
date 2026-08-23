"""
dashboard/pdf_charts.py — Gráficas e imágenes del Informe DLP.

Rasterizado de figuras Plotly (kaleido), las dos gráficas propias del PDF
(tendencia del precio y recorrido del precio con anti-colisión de etiquetas),
el logo con halo y el QR del CTA. Cero llamadas a Anthropic.
"""
import io
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage
import qrcode
from reportlab.lib.utils import ImageReader

from dashboard.pdf_rules import _to_float

ASSETS_DIR = Path(__file__).parent.parent / "assets"


def _autodetect_logo() -> Optional[Path]:
    """Cualquier imagen en assets/ (prioridad: nombre con 'logo', luego 'dlp')."""
    if not ASSETS_DIR.exists():
        return None
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    images = [p for p in ASSETS_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts]
    if not images:
        return None
    return sorted(images, key=lambda p: (0 if "logo" in p.name.lower() else 1,
                                         0 if "dlp" in p.name.lower() else 1,
                                         p.name.lower()))[0]


LOGO_PATH = _autodetect_logo()


# ── Plotly → PNG ────────────────────────────────────────────────────────
def _chart_png(fig, width_px: int, height_px: int) -> Optional[ImageReader]:
    try:
        png = fig.to_image(format="png", width=width_px, height=height_px,
                           scale=2, engine="kaleido")
        return ImageReader(io.BytesIO(png))
    except Exception:
        return None


def _chart_png_fiel(fig, width_px: int, height_px: int, scale: int = 5) -> Optional[ImageReader]:
    """Rasteriza una figura TAL COMO SE VE EN LA APP, solo a más resolución:
    tamaño lógico real del componente + `scale`, para que las fuentes de la
    figura no salgan como motas."""
    try:
        png = fig.to_image(format="png", width=width_px, height=height_px,
                           scale=scale, engine="kaleido")
        return ImageReader(io.BytesIO(png))
    except Exception:
        return None


# ── Logo con esquinas redondeadas + halo ─────────────────────────────────
def _styled_logo_png(logo_path: Path, max_dim_px: int = 900,
                     corner_radius_pct: float = 0.10,
                     glow_color=(255, 184, 77), glow_blur: int = 24,
                     glow_intensity: float = 0.65, pad_px: int = 60) -> Optional[ImageReader]:
    try:
        from PIL import ImageDraw, ImageFilter
        img = PILImage.open(str(logo_path)).convert("RGBA")
        ow, oh = img.size
        if ow >= oh:
            tw, th = max_dim_px, int(oh * max_dim_px / ow)
        else:
            th, tw = max_dim_px, int(ow * max_dim_px / oh)
        img = img.resize((tw, th), PILImage.LANCZOS)
        mask = PILImage.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw, th),
                                               radius=int(min(tw, th) * corner_radius_pct), fill=255)
        img.putalpha(mask)
        cw, ch = tw + 2 * pad_px, th + 2 * pad_px
        out = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
        glow = PILImage.new("RGBA", (tw, th), glow_color + (int(255 * glow_intensity),))
        glow.putalpha(mask)
        layer = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
        layer.paste(glow, (pad_px, pad_px), glow)
        out = PILImage.alpha_composite(out, layer.filter(ImageFilter.GaussianBlur(glow_blur)))
        shadow = PILImage.new("RGBA", (tw, th), (0, 0, 0, 130))
        shadow.putalpha(mask)
        layer = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
        layer.paste(shadow, (pad_px + 5, pad_px + 7), shadow)
        out = PILImage.alpha_composite(out, layer.filter(ImageFilter.GaussianBlur(8)))
        out.paste(img, (pad_px, pad_px), img)
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


# ── QR ──────────────────────────────────────────────────────────────────
def _qr_image(url: str, size_px: int = 480, fill: str = "#0A0B0D",
              back: str = "#F4EBD6") -> Optional[ImageReader]:
    """QR con módulos OSCUROS sobre fondo claro: el único que leen todas las
    cámaras (el oro sobre negro de antes no era fiable)."""
    try:
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill, back_color=back)
        pil = img.get_image() if hasattr(img, "get_image") else img
        pil = pil.convert("RGB").resize((size_px, size_px), PILImage.LANCZOS)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


# ── Serie de cierres del análisis ────────────────────────────────────────
def _serie_cierres(a):
    tech = (getattr(a, "reports", None) or {}).get("technical")
    rd = getattr(tech, "raw_data", None) or {}
    df = rd.get("df_daily", {}) or {}
    close = df.get("Close", {}) if isinstance(df, dict) else {}
    if not close:
        return None, None
    series = [(d, _to_float(close[d])) for d in sorted(close.keys())]
    series = [(d, p) for d, p in series if p is not None]
    if len(series) < 20:
        return None, None
    return [s[0] for s in series], [s[1] for s in series]


_FONT_STACK = "Inter, Helvetica Neue, Helvetica, Arial, sans-serif"


def _build_simple_price_chart(a):
    """Línea de precio con halo y relleno degradado — sin velas ni indicadores."""
    import plotly.graph_objects as go
    dates, prices = _serie_cierres(a)
    if not dates:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
                             line=dict(color="rgba(226,178,92,0.14)", width=11,
                                       shape="spline", smoothing=0.5),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
                             line=dict(color="#E2B25C", width=3.5, shape="spline", smoothing=0.5),
                             fill="tozeroy", fillcolor="rgba(226,178,92,0.08)",
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[dates[-1]], y=[prices[-1]], mode="markers",
                             marker=dict(size=16, color="#F0C878", line=dict(width=3, color="white")),
                             hoverinfo="skip", showlegend=False))
    min_p, max_p = min(prices), max(prices)
    pad = (max_p - min_p) * 0.12
    fig.update_layout(
        paper_bgcolor="#101216", plot_bgcolor="#101216",
        margin=dict(l=110, r=60, t=30, b=60),
        font=dict(family=_FONT_STACK, color="#C9CDD3", size=24),
        xaxis=dict(showgrid=False, showline=False, tickfont=dict(size=20, color="#8D949E"),
                   tickformat="%b %Y", nticks=6),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", gridwidth=1,
                   tickfont=dict(size=20, color="#8D949E"), tickprefix="$",
                   range=[max(0, min_p - pad), max_p + pad]),
        showlegend=False,
    )
    return fig


def _build_price_journey_chart(a):
    """Línea de precio + niveles Mínimo / Actual / Potencial con etiquetas que
    NUNCA se pisan (separación mínima del 20 % del eje, medida en el PDF real)."""
    import plotly.graph_objects as go
    dates, prices = _serie_cierres(a)
    if not dates:
        return None
    cur_f = _to_float(getattr(a, "entry_price", None))
    min_f = _to_float(getattr(a, "stop_loss", None))
    pot_f = _to_float(getattr(a, "target_price", None))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
                             line=dict(color="rgba(226,178,92,0.14)", width=11, shape="spline", smoothing=0.5),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
                             line=dict(color="#E2B25C", width=3.5, shape="spline", smoothing=0.5),
                             fill="tozeroy", fillcolor="rgba(226,178,92,0.08)",
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[dates[-1]], y=[prices[-1]], mode="markers",
                             marker=dict(size=16, color="#F0C878", line=dict(width=3, color="white")),
                             hoverinfo="skip", showlegend=False))

    all_pts = prices + [v for v in (cur_f, min_f, pot_f) if v is not None]
    min_p, max_p = min(all_pts), max(all_pts)
    pad = (max_p - min_p) * 0.08
    y_lo, y_hi = max(0, min_p - pad), max_p + pad
    y_span = (y_hi - y_lo) or 1.0

    niveles = [(v, n, col, dash) for v, n, col, dash in (
        (min_f, "Mínimo", "#F1495F", "dash"),
        (cur_f, "Actual", "#E2B25C", "dot"),
        (pot_f, "Potencial", "#3DD68C", "dash"),
    ) if v is not None]
    niveles.sort(key=lambda n: n[0])

    MIN_SEP = y_span * 0.20
    label_y = [n[0] for n in niveles]
    for i in range(1, len(label_y)):
        if label_y[i] - label_y[i - 1] < MIN_SEP:
            label_y[i] = label_y[i - 1] + MIN_SEP
    if label_y:
        exceso = label_y[-1] - (y_hi - MIN_SEP * 0.35)
        if exceso > 0:
            label_y = [y - exceso for y in label_y]
            label_y[0] = max(label_y[0], y_lo + MIN_SEP * 0.35)
            for i in range(1, len(label_y)):
                if label_y[i] - label_y[i - 1] < MIN_SEP:
                    label_y[i] = label_y[i - 1] + MIN_SEP

    shapes, annotations = [], []
    for (valor, nombre, color, dash), y_lbl in zip(niveles, label_y):
        shapes.append(dict(type="line", x0=dates[0], x1=dates[-1], y0=valor, y1=valor,
                           xref="x", yref="y", line=dict(color=color, width=2, dash=dash)))
        annotations.append(dict(x=1, xref="paper", y=y_lbl, yref="y", xanchor="left",
                                yanchor="middle", text=f"  <b>{nombre}</b><br>  ${valor:,.0f}",
                                showarrow=False, font=dict(size=20, color=color, family=_FONT_STACK)))

    fig.update_layout(
        paper_bgcolor="#101216", plot_bgcolor="#101216",
        margin=dict(l=110, r=200, t=30, b=60),
        font=dict(family=_FONT_STACK, color="#C9CDD3", size=22),
        xaxis=dict(showgrid=False, showline=False, tickfont=dict(size=20, color="#8D949E"),
                   tickformat="%b %Y", nticks=6),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   tickfont=dict(size=20, color="#8D949E"), tickprefix="$", range=[y_lo, y_hi]),
        showlegend=False, shapes=shapes, annotations=annotations,
    )
    return fig
