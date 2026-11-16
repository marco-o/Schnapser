"""Cuts the picture of the four suit signs into one image per suit.

  python scripts/cut_suits.py SUITS.png OUT_DIR [--order csdh]

The picture shows the signs side by side on a transparent background; by
default, left to right: Kreuz (acorn), Pik (leaf), Caro (bell), Herz
(heart). Neighbouring signs are split at the emptiest column between them,
so signs that touch, or have detached bits such as a stem, still come out
whole and clean. Each is saved as
OUT_DIR/<suit>.png (the client's suit codes c, s, d, h), centred on a
transparent square.
"""

import argparse
import os

import numpy as np
from PIL import Image
from scipy import ndimage


def main() -> None:
  p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
  p.add_argument("picture")
  p.add_argument("out_dir")
  p.add_argument("--order", default="csdh", help="suit of each sign, left first")
  a = p.parse_args()
  if sorted(a.order) != sorted("cdhs"):
    raise SystemExit("--order must order c, d, h, s")
  rgba = np.asarray(Image.open(a.picture).convert("RGBA"))
  alpha = rgba[..., 3] > 0
  labels, n = ndimage.label(alpha)
  sizes = ndimage.sum(alpha, labels, range(1, n + 1))
  big = np.argsort(sizes)[-4:] + 1
  centers = sorted(ndimage.center_of_mass(alpha, labels, l)[1] for l in big)
  # Split between neighbouring signs at the emptiest column between their
  # centres (signs may touch, or have detached bits like a stem).
  cov = alpha.sum(axis=0)
  cuts = [0]
  for left, right in zip(centers, centers[1:]):
    lo, hi = int(left), int(right) + 1
    low = cov[lo:hi].min()
    cols = np.where(cov[lo:hi] == low)[0] + lo
    cuts.append(int(cols[len(cols) // 2]))
  cuts.append(alpha.shape[1])
  owner = np.zeros(alpha.shape, np.int32)
  for i in range(4):
    owner[:, cuts[i] : cuts[i + 1]] = i + 1
  owner[~alpha] = 0
  os.makedirs(a.out_dir, exist_ok=True)
  for i, suit in enumerate(a.order):
    mask = owner == i + 1
    # Keep the sign's main shape and the pieces touching it (within 1 px);
    # drop stray marks that only happen to lie in its columns.
    parts, m = ndimage.label(mask)
    if m > 1:
      areas = ndimage.sum(mask, parts, range(1, m + 1))
      main = parts == int(np.argmax(areas)) + 1
      near = ndimage.binary_dilation(main, iterations=2)
      keep = main.copy()
      for k in range(1, m + 1):
        piece = parts == k
        if (piece & near).any():
          keep |= piece
      mask = keep
    ys, xs = np.where(mask)
    img = rgba.copy()
    img[~mask] = 0
    crop = img[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    h, w = crop.shape[:2]
    side = max(h, w) + 2
    square = np.zeros((side, side, 4), np.uint8)
    y0, x0 = (side - h) // 2, (side - w) // 2
    square[y0 : y0 + h, x0 : x0 + w] = crop
    Image.fromarray(square).save(os.path.join(a.out_dir, f"{suit}.png"), optimize=True)
    print(f"{suit}: {w}x{h} -> {side}x{side}")


if __name__ == "__main__":
  main()
