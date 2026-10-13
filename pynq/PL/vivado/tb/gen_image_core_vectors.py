from __future__ import annotations

import argparse
from pathlib import Path

from gen_pixel_core_vectors import BRANCHES, calc_pixel, read_mem


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def lr_at(lr: list[int], width: int, height: int, x: int, y: int) -> int:
    x = clamp(x, 0, width - 1)
    y = clamp(y, 0, height - 1)
    return lr[y * width + x]


def pixel_inputs(lr: list[int], width: int, height: int, x: int, y: int) -> list[int]:
    return [
        lr_at(lr, width, height, x - 2, y),
        lr_at(lr, width, height, x - 1, y),
        lr_at(lr, width, height, x, y),
        lr_at(lr, width, height, x, y),
        lr_at(lr, width, height, x + 1, y),
        lr_at(lr, width, height, x + 2, y),
        lr_at(lr, width, height, x, y - 2),
        lr_at(lr, width, height, x, y - 1),
        lr_at(lr, width, height, x, y),
        lr_at(lr, width, height, x, y),
        lr_at(lr, width, height, x, y + 1),
        lr_at(lr, width, height, x, y + 2),
    ]


def build_lr(width: int, height: int) -> list[int]:
    values: list[int] = []
    for y in range(height):
        for x in range(width):
            values.append((17 * x + 41 * y + 13 * x * y) & 0xFF)
    return values


def write_mem(path: Path, values: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for v in values:
            f.write(f"{v & 0xFF:02x}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LR/HR golden memories for pimsr_image_core RTL.")
    parser.add_argument("--lut-dir", type=Path, default=Path("../lut_sampled_4bit_qat_early_swa"))
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument("--height", type=int, default=4)
    parser.add_argument("--lr-output", type=Path, default=Path("image_core_lr_4x4.mem"))
    parser.add_argument("--hr-output", type=Path, default=Path("image_core_hr_8x8.mem"))
    args = parser.parse_args()

    luts = {branch: read_mem(args.lut_dir / f"{branch}_4bit.mem") for branch in BRANCHES}
    lr = build_lr(args.width, args.height)
    hr = [0] * (args.width * 2 * args.height * 2)

    for y in range(args.height):
        for x in range(args.width):
            tl, tr, bl, br = calc_pixel(luts, pixel_inputs(lr, args.width, args.height, x, y))
            hx = x * 2
            hy = y * 2
            hr_width = args.width * 2
            hr[hy * hr_width + hx] = tl
            hr[hy * hr_width + hx + 1] = tr
            hr[(hy + 1) * hr_width + hx] = bl
            hr[(hy + 1) * hr_width + hx + 1] = br

    write_mem(args.lr_output, lr)
    write_mem(args.hr_output, hr)
    print(f"wrote LR {args.width}x{args.height} to {args.lr_output}")
    print(f"wrote HR {args.width * 2}x{args.height * 2} to {args.hr_output}")


if __name__ == "__main__":
    main()
