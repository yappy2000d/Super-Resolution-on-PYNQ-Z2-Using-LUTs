from __future__ import annotations

import argparse
import random
from pathlib import Path


BRANCHES = ("left", "right", "top", "bot")


def sx8(v: int) -> int:
    v &= 0xFF
    return v - 256 if v & 0x80 else v


def clamp_s8(v: int) -> int:
    return max(-128, min(127, v))


def clamp_u8(v: int) -> int:
    return max(0, min(255, v))


def round_shift4(v: int) -> int:
    if v >= 0:
        return (v + 8) >> 4
    return (v - 8) >> 4


def read_mem(path: Path) -> list[int]:
    words: list[int] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                words.append(int(line, 16))
    if len(words) != 4096:
        raise ValueError(f"{path} has {len(words)} words, expected 4096")
    return words


def word_ch(word: int, ch: int) -> int:
    shift = (3 - ch) * 8
    return sx8((word >> shift) & 0xFF)


def pack_addr(a: int, b: int, c: int) -> int:
    return ((a & 0xF) << 8) | ((b & 0xF) << 4) | (c & 0xF)


def interp_branch(lut: list[int], p0: int, p1: int, p2: int) -> list[int]:
    i0, i1, i2 = p0 >> 4, p1 >> 4, p2 >> 4
    h0 = 0xF if i0 == 0xF else i0 + 1
    h1 = 0xF if i1 == 0xF else i1 + 1
    h2 = 0xF if i2 == 0xF else i2 + 1
    f0 = 0 if i0 == 0xF else p0 & 0xF
    f1 = 0 if i1 == 0xF else p1 & 0xF
    f2 = 0 if i2 == 0xF else p2 & 0xF

    v000 = lut[pack_addr(i0, i1, i2)]
    v100 = lut[pack_addr(h0, i1, i2)]
    v010 = lut[pack_addr(i0, h1, i2)]
    v001 = lut[pack_addr(i0, i1, h2)]
    v110 = lut[pack_addr(h0, h1, i2)]
    v101 = lut[pack_addr(h0, i1, h2)]
    v011 = lut[pack_addr(i0, h1, h2)]
    v111 = lut[pack_addr(h0, h1, h2)]

    out: list[int] = []
    for ch in range(4):
        base = word_ch(v000, ch)
        third = word_ch(v111, ch)

        if f0 >= f1 and f1 >= f2:
            first, second, w1, w2, w3 = word_ch(v100, ch), word_ch(v110, ch), f0, f1, f2
        elif f0 >= f2 and f2 > f1:
            first, second, w1, w2, w3 = word_ch(v100, ch), word_ch(v101, ch), f0, f2, f1
        elif f1 > f0 and f0 >= f2:
            first, second, w1, w2, w3 = word_ch(v010, ch), word_ch(v110, ch), f1, f0, f2
        elif f1 >= f2 and f2 > f0:
            first, second, w1, w2, w3 = word_ch(v010, ch), word_ch(v011, ch), f1, f2, f0
        elif f2 > f0 and f0 >= f1:
            first, second, w1, w2, w3 = word_ch(v001, ch), word_ch(v101, ch), f2, f0, f1
        else:
            first, second, w1, w2, w3 = word_ch(v001, ch), word_ch(v011, ch), f2, f1, f0

        acc = (
            base
            + round_shift4(w1 * (first - base))
            + round_shift4(w2 * (second - first))
            + round_shift4(w3 * (third - second))
        )
        out.append(clamp_s8(acc))
    return out


def calc_pixel(luts: dict[str, list[int]], inputs: list[int]) -> list[int]:
    ys = []
    for idx, branch in enumerate(BRANCHES):
        p0, p1, p2 = inputs[idx * 3 : idx * 3 + 3]
        ys.append(interp_branch(luts[branch], p0, p1, p2))
    return [clamp_u8(sum(y[ch] for y in ys)) for ch in range(4)]


def pack_vector(inputs: list[int], outputs: list[int]) -> str:
    values = inputs + outputs
    if len(values) != 16:
        raise ValueError("expected 12 input bytes plus 4 output bytes")
    return "".join(f"{v & 0xFF:02x}" for v in values)


def build_cases(random_count: int, seed: int) -> list[list[int]]:
    cases = [
        [0] * 12,
        [128] * 12,
        [255] * 12,
        [10, 20, 30, 30, 40, 50, 60, 70, 80, 80, 90, 100],
        [0, 15, 16, 31, 32, 47, 48, 63, 64, 79, 80, 95],
        [240, 241, 255, 255, 254, 240, 128, 144, 159, 15, 1, 0],
    ]
    rng = random.Random(seed)
    for _ in range(random_count):
        cases.append([rng.randrange(256) for _ in range(12)])
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate golden vectors for pimsr_lut_pixel_core RTL.")
    parser.add_argument("--lut-dir", type=Path, default=Path("../lut_sampled_4bit_qat_early_swa"))
    parser.add_argument("--output", type=Path, default=Path("pixel_core_vectors.mem"))
    parser.add_argument("--random-count", type=int, default=256)
    parser.add_argument("--seed", type=int, default=20260622)
    args = parser.parse_args()

    luts = {branch: read_mem(args.lut_dir / f"{branch}_4bit.mem") for branch in BRANCHES}
    cases = build_cases(args.random_count, args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for inputs in cases:
            outputs = calc_pixel(luts, inputs)
            f.write(pack_vector(inputs, outputs))
            f.write("\n")

    print(f"wrote {len(cases)} vectors to {args.output}")


if __name__ == "__main__":
    main()
