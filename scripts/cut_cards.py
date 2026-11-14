"""Cuts a picture of the 20 schnaps cards into one image per card.

  # the sheet in use: separate cards on a transparent background,
  # rows Caro, Herz, Pik, Kreuz; columns Zehn, Unter, Ober, Koenig, As
  python scripts/cut_cards.py schnapser-1.png OUT_DIR --transparent \
      --rows dhsc --cols TJQKA
  # the earlier photo on a wooden table (the defaults below)
  python scripts/cut_cards.py Schnapser.png OUT_DIR [--preview PREVIEW.png]

--rows and --cols give the layout: the suit of each row from the top (c, s,
h, d: Kreuz, Pik, Herz, Caro) and the rank of each column from the left (A,
K, Q, J, T: As, Koenig, Ober, Unter, Zehn).

A transparent sheet is cut along the transparency, keeping the cards' own
size and their transparent corners.

The photo (defaults: rows Kreuz, Pik, Herz, Caro; columns As, Koenig, Ober,
Unter, Zehn) shows the cards on a wooden table. Cards cut off at the
photo's edge are ignored.

Each card is found as a bright, unsaturated region (the paper) against the
wood, straightened by the slope of its left and right edges, trimmed to the
paper and saved as OUT_DIR/<code>.webp at a common size. Codes are the
client's: rank A, K, Q (Ober), J (Unter), T (Zehn) and suit c, s, h, d
(Kreuz, Pik, Herz, Caro).
"""

import argparse
import math
import os

import numpy as np
from PIL import Image
from scipy import ndimage

ROWS = ("c", "s", "h", "d")  # Kreuz, Pik, Herz, Caro
COLS = ("A", "K", "Q", "J", "T")  # As, Koenig, Ober, Unter, Zehn
OUT_W, OUT_H = 300, 480


def paper_mask(rgb: np.ndarray) -> np.ndarray:
  """Pixels of card paper or art: everything but the wooden table."""
  r, g, b = (rgb[..., i].astype(np.int32) for i in range(3))
  hi = np.maximum(np.maximum(r, g), b)
  lo = np.minimum(np.minimum(r, g), b)
  paper = (lo > 175) & (hi - lo < 40)
  # The cards' borders are paper; fill each card's inside.
  paper = ndimage.binary_opening(paper, iterations=2)
  return ndimage.binary_fill_holes(paper)


def edge_angle(mask: np.ndarray) -> float:
  """The card's tilt in degrees, from its left and right edges."""
  ys = np.arange(mask.shape[0])
  rows = mask.any(axis=1)
  ys = ys[rows]
  # Use the middle 70% of the height (corners are rounded).
  lo, hi = ys[0], ys[-1]
  keep = (ys > lo + 0.15 * (hi - lo)) & (ys < hi - 0.15 * (hi - lo))
  ys = ys[keep]
  left = np.array([np.argmax(mask[y]) for y in ys])
  right = np.array([mask.shape[1] - 1 - np.argmax(mask[y][::-1]) for y in ys])
  slopes = [np.polyfit(ys, x, 1)[0] for x in (left, right)]
  return math.degrees(math.atan(float(np.mean(slopes))))


def _tilt(mask: np.ndarray) -> float:
  """The card's tilt in degrees from its left and right edges (0 if unsure)."""
  try:
    raw = edge_angle(mask)
  except (ValueError, TypeError, np.linalg.LinAlgError):
    return 0.0
  return raw if abs(raw) <= 2.5 else 0.0


def _trim_dark_edges(img: Image.Image, limit: int = 20) -> Image.Image:
  """Trims edge strips that are table, not paper (darker than the border)."""
  a = np.asarray(img.convert("L")).astype(np.float32)
  top, bottom, left, right = 0, a.shape[0], 0, a.shape[1]
  dark = 0.85 * np.median(a[a.shape[0] // 4 : 3 * a.shape[0] // 4, :12])
  dark = min(dark, 0.85 * np.percentile(a, 90))
  for _ in range(limit):
    if a[top:bottom, left].mean() < dark:
      left += 1
    if a[top:bottom, right - 1].mean() < dark:
      right -= 1
    if a[top, left:right].mean() < dark:
      top += 1
    if a[bottom - 1, left:right].mean() < dark:
      bottom -= 1
  return img.crop((left, top, right, bottom))


def cards(photo: Image.Image):
  """[(row, col, card image, tilt)] for the 20 cards (module doc).

  The paper regions give each card's box. A card whose outline didn't close
  (shadows, art reaching the border) gives a box that is too small; it is
  grown from its far edge, the one toward the next card, to the size of the
  whole cards. Cards cut off at the photo's right edge are ignored.
  """
  rgb = np.asarray(photo.convert("RGB"))
  h, w = rgb.shape[:2]
  mask = paper_mask(rgb)
  labels, _ = ndimage.label(mask)
  boxes = [
      (i + 1, b) for i, b in enumerate(ndimage.find_objects(labels))
      if b is not None and (b[0].stop - b[0].start) > 120
      and (b[1].stop - b[1].start) > 120
  ]
  sizes = sorted(
      ((b[1].stop - b[1].start), (b[0].stop - b[0].start)) for _, b in boxes
  )
  card_w = int(np.median([s[0] for s in sizes[-20:]]))
  card_h = int(np.median([s[1] for s in sizes[-20:]]))
  # Rows: cluster the boxes by their vertical middle.
  row_h = h / 4
  slots: dict = {}
  for label, (ys, xs) in boxes:
    yc = (ys.start + ys.stop) / 2
    ri = min(int(yc // row_h), 3)
    slots.setdefault(ri, []).append((label, ys, xs))
  out = []
  for ri in range(4):
    row = sorted(slots.get(ri, []), key=lambda t: t[2].stop)
    # Merge pieces of one card (same column) by their right edges.
    cols: list = []
    for label, ys, xs in row:
      if cols and xs.stop - cols[-1][2].stop < 0.5 * card_w:
        prev = cols[-1]
        if (prev[2].stop - prev[2].start) < (xs.stop - xs.start):
          cols[-1] = (label, ys, xs)
        continue
      cols.append((label, ys, xs))
    cols = [c for c in cols if c[2].stop < w - 3 or c[2].stop - c[2].start > 0.9 * card_w]
    cols = [c for c in cols if c[2].start > 3 or c[2].stop - c[2].start > 0.5 * card_w]
    cols = [c for c in cols if c[2].stop <= w - 3]
    if len(cols) < 5:
      raise SystemExit(f"row {ri}: found {len(cols)} cards, not 5")
    for ci, (label, ys, xs) in enumerate(cols[:5]):
      x1 = xs.stop
      x0 = xs.start if xs.stop - xs.start > 0.95 * card_w else max(x1 - card_w, 0)
      y0 = ys.start
      y1 = ys.stop if ys.stop - ys.start > 0.95 * card_h else min(y0 + card_h, h)
      if ys.stop - ys.start <= 0.95 * card_h and y0 > 0.5 * row_h * 0:
        # A short box: anchor it at whichever edge looks like the card's.
        y1 = min(max(ys.stop, y0 + card_h), h)
        y0 = max(y1 - card_h, 0)
      cell_mask = labels[y0:y1, x0:x1] == label
      angle = _tilt(cell_mask) if cell_mask.mean() > 0.8 else 0.0
      img = photo.crop((x0, y0, x1, y1))
      if angle:
        img = img.rotate(-angle, resample=Image.BICUBIC, fillcolor=(240, 240, 235))
      inset = max(3, int(round(abs(math.tan(math.radians(angle))) * card_h / 2)) + 2)
      img = img.crop((inset, inset, img.size[0] - inset, img.size[1] - inset))
      out.append((ri, ci, _trim_dark_edges(img), angle))
  return out


def cards_from_transparent(sheet: Image.Image):
  """[(row, col, card image, 0.0)] from a sheet with a transparent background.

  Every card is a separate opaque region; anything much bigger or smaller
  than a card (a frame round the sheet, specks) is ignored. Corners keep
  their transparency.
  """
  rgba = sheet.convert("RGBA")
  alpha = np.asarray(rgba)[..., 3] > 0
  labels, _ = ndimage.label(alpha)
  boxes = [b for b in ndimage.find_objects(labels) if b is not None]
  areas = [(b[0].stop - b[0].start) * (b[1].stop - b[1].start) for b in boxes]
  typical = np.median(sorted(areas)[-21:-1]) if len(areas) > 20 else np.median(areas)
  cards_ = [b for b, a in zip(boxes, areas) if 0.6 * typical < a < 1.6 * typical]
  if len(cards_) != 20:
    raise SystemExit(f"found {len(cards_)} cards, not 20")
  cards_.sort(key=lambda b: (b[0].start + b[0].stop) / 2)
  out = []
  for r in range(4):
    row = sorted(cards_[5 * r : 5 * r + 5], key=lambda b: b[1].start)
    for c, (ys, xs) in enumerate(row):
      # Trim edge columns and rows that are mostly transparent (a stray line
      # touching the card), so the card isn't squeezed when resized.
      cov = alpha[ys, xs]
      col_cov, row_cov = cov.mean(axis=0), cov.mean(axis=1)
      cx = np.where(col_cov > 0.5)[0]
      cy = np.where(row_cov > 0.5)[0]
      box = (xs.start + cx[0], ys.start + cy[0], xs.start + cx[-1] + 1, ys.start + cy[-1] + 1)
      out.append((r, c, rgba.crop(box), 0.0))
  return out


def main() -> None:
  p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
  p.add_argument("photo")
  p.add_argument("out_dir")
  p.add_argument("--preview", default="")
  p.add_argument(
      "--transparent", action="store_true",
      help="a sheet of separate cards on a transparent background",
  )
  p.add_argument("--rows", default="".join(ROWS), help="suit of each row, top first")
  p.add_argument("--cols", default="".join(COLS), help="rank of each column, left first")
  p.add_argument("--size", default="", help="output WxH (default: the photo's 300x480, or the sheet's own card size)")
  a = p.parse_args()
  rows, cols = tuple(a.rows), tuple(a.cols)
  if sorted(rows) != sorted("cdhs") or sorted(cols) != sorted("AJKQT"):
    raise SystemExit("--rows must order c, d, h, s and --cols A, J, K, Q, T")
  img = Image.open(a.photo)
  found = cards_from_transparent(img) if a.transparent else cards(img.convert("RGB"))
  if a.size:
    out_w, out_h = (int(v) for v in a.size.lower().split("x"))
  elif a.transparent:
    out_w = int(np.median([c[2].size[0] for c in found]))
    out_h = int(np.median([c[2].size[1] for c in found]))
  else:
    out_w, out_h = OUT_W, OUT_H
  os.makedirs(a.out_dir, exist_ok=True)
  sheet = Image.new("RGBA", (5 * (out_w + 8), 4 * (out_h + 8)), (255, 255, 255, 255))
  for r, c, card_img, angle in found:
    code = cols[c] + rows[r]
    card = card_img.resize((out_w, out_h), Image.LANCZOS)
    card.save(os.path.join(a.out_dir, f"{code}.webp"), quality=90, method=6)
    sheet.alpha_composite(card.convert("RGBA"), (c * (out_w + 8), r * (out_h + 8)))
    print(f"{code}: {card_img.size[0]}x{card_img.size[1]}, tilt {angle:+.2f} deg")
  if a.preview:
    sheet.save(a.preview)


if __name__ == "__main__":
  main()
