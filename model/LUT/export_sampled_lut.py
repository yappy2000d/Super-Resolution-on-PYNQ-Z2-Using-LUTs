import argparse
import json
from pathlib import Path

import numpy as np

from pimsr_lut import BRANCHES, LUT_ENTRY_WIDTH, address_from_pixels, load_lut_file


def entry_to_hex(entry: np.ndarray) -> str:
    return "".join(f"{int(v) & 0xFF:02x}" for v in entry)


def write_coe_words(words: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        f.write("memory_initialization_radix=16;\n")
        f.write("memory_initialization_vector=\n")
        last = len(words) - 1
        for idx, word in enumerate(words):
            f.write(word)
            f.write(";\n" if idx == last else ",\n")


def sampled_full_address(sample_addr: int, input_bits: int) -> int:
    q2 = sample_addr & ((1 << input_bits) - 1)
    q1 = (sample_addr >> input_bits) & ((1 << input_bits) - 1)
    q0 = (sample_addr >> (2 * input_bits)) & ((1 << input_bits) - 1)
    shift = 8 - input_bits
    p0 = np.array(q0 << shift, dtype=np.uint8)
    p1 = np.array(q1 << shift, dtype=np.uint8)
    p2 = np.array(q2 << shift, dtype=np.uint8)
    return int(address_from_pixels(p0, p1, p2))


def export_sampled_branch(
    full_lut_path: Path,
    output_mem_path: Path,
    input_bits: int,
    output_coe_path: Path | None = None,
) -> None:
    depth = 1 << (3 * input_bits)
    full_lut = load_lut_file(full_lut_path, mmap=True)
    output_mem_path.parent.mkdir(parents=True, exist_ok=True)

    coe_words = [] if output_coe_path is not None else None
    with output_mem_path.open("w") as f:
        for sample_addr in range(depth):
            full_addr = sampled_full_address(sample_addr, input_bits)
            word = entry_to_hex(full_lut[full_addr])
            f.write(word)
            f.write("\n")
            if coe_words is not None:
                coe_words.append(word)

    if output_coe_path is not None:
        write_coe_words(coe_words, output_coe_path)


def export_sampled_luts(
    full_lut_dir: Path,
    output_dir: Path,
    input_bits: int,
    write_coe: bool = False,
) -> None:
    if input_bits < 1 or input_bits > 8:
        raise ValueError("input_bits must be in 1..8")

    output_dir.mkdir(parents=True, exist_ok=True)
    for branch in BRANCHES:
        export_sampled_branch(
            full_lut_path=full_lut_dir / f"{branch}.bin",
            output_mem_path=output_dir / f"{branch}_{input_bits}bit.mem",
            input_bits=input_bits,
            output_coe_path=output_dir / f"{branch}_{input_bits}bit.coe" if write_coe else None,
        )

    metadata = {
        "source_full_lut_dir": str(full_lut_dir),
        "input_bits": input_bits,
        "address": "addr = {p0[7:8-input_bits], p1[7:8-input_bits], p2[7:8-input_bits]}",
        "depth_per_branch": 1 << (3 * input_bits),
        "word_width_bits": LUT_ENTRY_WIDTH * 8,
        "word_order": {
            "[31:24]": "top_left signed int8",
            "[23:16]": "top_right signed int8",
            "[15:8]": "bottom_left signed int8",
            "[7:0]": "bottom_right signed int8",
        },
        "sample_level": "sample = msb_index << (8 - input_bits)",
        "edge_policy": "if msb_index is max, interpolation fraction is forced to zero",
        "formats": ["mem", "coe"] if write_coe else ["mem"],
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export PIMSR sampled LUTs for Vivado BRAM.")
    parser.add_argument("--full-lut-dir", type=Path, default=Path("lut_out"))
    parser.add_argument("--output-dir", type=Path, default=Path("vivado/lut_sampled_4bit"))
    parser.add_argument("--input-bits", type=int, default=4)
    parser.add_argument("--write-coe", action="store_true", help="also emit Vivado Block Memory Generator .coe files")
    args = parser.parse_args()

    export_sampled_luts(args.full_lut_dir, args.output_dir, args.input_bits, write_coe=args.write_coe)


if __name__ == "__main__":
    main()
