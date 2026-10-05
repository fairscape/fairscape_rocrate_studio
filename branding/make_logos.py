"""Generate RO-Crate Studio logo SVGs (text outlined with fontTools, no font dependency)."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

OUT = Path(__file__).parent
FONTS = "/usr/share/fonts/truetype/ubuntu/"
BOLD, MED, REG = (TTFont(FONTS + f) for f in ("Ubuntu-B.ttf", "Ubuntu-M.ttf", "Ubuntu-R.ttf"))

INK, ACCENT = "#1c2128", "#2f6fed"
# studio entity colours: dataset, software, computation, schema
CHIPS = ["#3b82f6", "#8b5cf6", "#f59e0b", "#10b981"]


def text(font, s, size, x, y, spacing=0.0):
    """Return (path_d, advance_width) for s with baseline at (x, y)."""
    gs, cmap = font.getGlyphSet(), font.getBestCmap()
    upm = font["head"].unitsPerEm
    k = size / upm
    pen = SVGPathPen(gs)
    cx = 0.0
    for ch in s:
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (k, 0, 0, -k, x + cx, y)))
        cx += gs[g].width * k + spacing
    return pen.getCommands(), cx - spacing


def braces(x0, x1, top, bot, w):
    """Left brace with outer tip at x0, right brace with outer tip at x1."""
    h, m = bot - top, (top + bot) / 2
    d = w * 0.75   # tip depth
    c = h * 0.07   # corner
    def side(t, s):  # t: tip x, s: +1 left, -1 right
        b = t + s * d          # brace spine
        e = b + s * d * 0.9    # end hooks
        return (f"M{e:.1f} {top} C{b:.1f} {top} {b:.1f} {top + c * .5:.1f} {b:.1f} {top + c:.1f} "
                f"C{b:.1f} {m - c * 1.6:.1f} {b:.1f} {m - c * .6:.1f} {t:.1f} {m} "
                f"C{b:.1f} {m + c * .6:.1f} {b:.1f} {m + c * 1.6:.1f} {b:.1f} {bot - c:.1f} "
                f"C{b:.1f} {bot - c * .5:.1f} {b:.1f} {bot} {e:.1f} {bot}")
    return side(x0, 1), side(x1, -1)


def svg(w, h, body, label):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w:.0f} {h:.0f}' width='{w:.0f}' "
            f"height='{h:.0f}' role='img' aria-label='{label}'>{body}</svg>\n")


def concept_a(ink=INK, accent=ACCENT):
    """{ FAIRSCAPE / Studio } — wordmark wrapped in braces, CSV header chips on top."""
    pad = 70
    f_d, f_w = text(BOLD, "FAIRSCAPE", 52, pad, 100, 3)
    s_d, s_w = text(REG, "Studio", 34, pad, 142, 1)
    W = pad * 2 + f_w
    L, R = braces(18, W - 18, 18, 162, 12)
    cw, gap = (f_w - 3 * 8) / 4, 8
    chips = "".join(f"<rect x='{pad + i * (cw + gap):.1f}' y='34' width='{cw:.1f}' height='12' rx='3' fill='{c}'/>"
                    for i, c in enumerate(CHIPS))
    # "Studio" sits left, followed by faint body cells to finish the row
    cells, cx = "", pad + s_w + 16
    while cx + 20 <= pad + f_w + 0.5:
        cells += f"<rect x='{cx:.1f}' y='118' width='20' height='22' rx='4' fill='{ink}' opacity='.14'/>"
        cx += 28
    body = (f"<g fill='none' stroke='{ink}' stroke-width='11' stroke-linecap='round' stroke-linejoin='round'>"
            f"<path d='{L}'/><path d='{R}'/></g>{chips}<path d='{f_d}' fill='{ink}'/>"
            f"<path d='{s_d}' fill='{accent}'/>{cells}")
    return svg(W, 180, body, "FAIRSCAPE Studio")


def concept_a_inline(ink=INK, accent=ACCENT):
    """One-line { FAIRSCAPE Studio } for the app header, where the stacked logo would be too small."""
    pad = 34
    f_d, f_w = text(BOLD, "FAIRSCAPE", 26, pad, 48, 1.5)
    s_d, s_w = text(REG, "Studio", 26, pad + f_w + 9, 48, 0.5)
    tw = f_w + 9 + s_w
    W = pad * 2 + tw
    L, R = braces(8, W - 8, 6, 58, 5.5)
    cw, gap = (tw - 3 * 5) / 4, 5
    chips = "".join(f"<rect x='{pad + i * (cw + gap):.1f}' y='12' width='{cw:.1f}' height='5' rx='2' fill='{c}'/>"
                    for i, c in enumerate(CHIPS))
    body = (f"<g fill='none' stroke='{ink}' stroke-width='5' stroke-linecap='round' stroke-linejoin='round'>"
            f"<path d='{L}'/><path d='{R}'/></g>{chips}<path d='{f_d}' fill='{ink}'/><path d='{s_d}' fill='{accent}'/>")
    return svg(W, 64, body, "FAIRSCAPE Studio")


def concept_b(ink=INK, paper="#ffffff"):
    """Braces around a table whose header row *is* the name."""
    pad, tx = 64, 64
    f_d, f_w = text(BOLD, "FAIRSCAPE STUDIO", 30, 0, 0, 2)
    tw = f_w + 44
    W = pad * 2 + tw
    f_d, _ = text(BOLD, "FAIRSCAPE STUDIO", 30, tx + 22, 63, 2)
    L, R = braces(16, W - 16, 18, 172, 11)
    rows = ""
    cols = 4
    cw = (tw - (cols - 1) * 8) / cols
    for r, y in enumerate((90, 128)):
        for c in range(cols):
            fill = CHIPS[c] if r == 0 else ink
            op = ".85" if r == 0 else ".14"
            rows += (f"<rect x='{tx + c * (cw + 8):.1f}' y='{y}' width='{cw:.1f}' height='28' rx='5' "
                     f"fill='{fill}' opacity='{op}'/>")
    body = (f"<g fill='none' stroke='{ink}' stroke-width='10' stroke-linecap='round' stroke-linejoin='round'>"
            f"<path d='{L}'/><path d='{R}'/></g>"
            f"<rect x='{tx}' y='30' width='{tw:.1f}' height='48' rx='7' fill='{ink}'/>"
            f"<path d='{f_d}' fill='{paper}'/>{rows}")
    return svg(W, 190, body, "FAIRSCAPE Studio")


def mark(size=100, bg=ACCENT, fg="#ffffff", tile=True):
    """Square icon: the Fairscape { grid } with studio-coloured header and one selected cell."""
    s = size / 100
    L = "M34 22 C28 22 28 26 28 30 C28 40 28 44 21 50 C28 56 28 60 28 70 C28 74 28 78 34 78"
    R = "M66 22 C72 22 72 26 72 30 C72 40 72 44 79 50 C72 56 72 60 72 70 C72 74 72 78 66 78"
    head = "".join(f"<rect x='{x}' y='34' width='6' height='6' rx='1.6' fill='{c}'/>"
                   for x, c in zip((38, 47, 56), ("#9cc3ff", "#c7b5ff", "#ffd27a") if tile else CHIPS))
    body_cells = "".join(f"<rect x='{x}' y='{y}' width='6' height='6' rx='1.6' fill='{fg}' opacity='.5'/>"
                         for y in (47, 60) for x in (38, 47, 56) if (x, y) != (56, 60))
    sel = (f"<rect x='54.5' y='58.5' width='9' height='9' rx='2.4' fill='none' stroke='{fg}' stroke-width='1.6'/>"
           f"<rect x='56' y='60' width='6' height='6' rx='1.6' fill='{fg}'/>")
    tile_el = f"<rect width='100' height='100' rx='22' fill='{bg}'/>" if tile else ""
    return (f"<g transform='scale({s})'>{tile_el}<g fill='none' stroke='{fg}' stroke-width='6' "
            f"stroke-linecap='round' stroke-linejoin='round'><path d='{L}'/><path d='{R}'/></g>"
            f"{head}{body_cells}{sel}</g>")


def concept_c(ink=INK, accent=ACCENT):
    """App-icon mark + stacked wordmark lockup."""
    f_d, f_w = text(BOLD, "FAIRSCAPE", 44, 140, 76, 2.5)
    s_d, s_w = text(REG, "Studio", 40, 140, 122, 0.5)
    W = 140 + max(f_w, s_w) + 20
    body = (f"<g transform='translate(10 15)'>{mark(110)}</g>"
            f"<path d='{f_d}' fill='{ink}'/><path d='{s_d}' fill='{accent}'/>")
    return svg(W, 140, body, "FAIRSCAPE Studio")


def icon():
    return svg(100, 100, mark(100), "FAIRSCAPE Studio")


def png(svg_file, out, width, pad=0.12, bg="#ffffff"):
    """Rasterise an SVG with headless Chrome onto a solid background, `width` px wide incl. padding."""
    w, h = map(float, re.search(r"viewBox='0 0 ([\d.]+) ([\d.]+)'", svg_file.read_text()).groups())
    p = round(w * pad)
    W, H = int(w + 2 * p), int(h + 2 * p)
    scale = width / W
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "p.html"
        page.write_text(f"<html><body style='margin:0;background:{bg}'><img src='{svg_file.resolve().as_uri()}' "
                        f"style='display:block;margin:{p}px;width:{w}px;height:{h}px'></body></html>")
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        "--default-background-color=00000000", f"--window-size={W},{H}", f"--force-device-scale-factor={scale}",
                        f"--screenshot={out}", page.as_uri()], check=True, capture_output=True)


if __name__ == "__main__":
    files = {
        "studio-logo-a.svg": concept_a(),
        "studio-logo-a-dark.svg": concept_a(ink="#e6e9ee", accent="#7aa5ff"),
        "studio-logo-b.svg": concept_b(),
        "studio-logo-b-dark.svg": concept_b(ink="#e6e9ee", paper="#14171c"),
        "studio-logo-a-inline.svg": concept_a_inline(),
        "studio-icon.svg": icon(),
    }
    for name, s in files.items():
        (OUT / name).write_text(s)
        print(name, len(s))

    # the app serves its copies from the package's static/ folder
    static = OUT.parent / "rocrate_studio" / "static"
    for name in ("studio-logo-a-inline.svg", "studio-icon.svg"):
        shutil.copy(OUT / name, static / name)

    pngs = OUT / "png"
    pngs.mkdir(exist_ok=True)
    for c in ("a", "b"):
        png(OUT / f"studio-logo-{c}.svg", pngs / f"studio-logo-{c}.png", 1600)          # slides, chat, README
        png(OUT / f"studio-logo-{c}.svg", pngs / f"studio-logo-{c}-poster.png", 6000)   # ~20in at 300 dpi
    big = pngs / "studio-icon-512.png"
    png(OUT / "studio-icon.svg", big, 512, pad=0, bg="transparent")
    from PIL import Image  # Chrome won't open a window under ~50px, so downscale the 512
    for n in (180, 32):
        Image.open(big).resize((n, n), Image.LANCZOS).save(pngs / f"studio-icon-{n}.png")
    print("pngs ->", pngs)
