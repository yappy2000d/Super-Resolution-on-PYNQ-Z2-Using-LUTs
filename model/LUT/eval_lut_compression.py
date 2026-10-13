import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as calculate_ssim

from pimsr_lut import (
    BRANCHES,
    FULL_LUT_DEPTH,
    LUT_ENTRY_WIDTH,
    PIMSRLUTSet,
    address_from_pixels,
    branch_windows,
    load_y_image,
    pixel_shuffle_x2,
)


VALID_EXTS = (".png", ".jpg", ".jpeg", ".bmp")
DEFAULT_DATASETS = (
    ("Set5", "Set5"),
    ("Set14", "Set14"),
    ("BSDS100", "BSDS100"),
    ("Urban100", "urban100"),
    ("Manga109", "manga109"),
)


@dataclass(frozen=True)
class CompressionConfig:
    name: str
    branch_input_bits: Mapping[str, int]
    channel_bits: Tuple[int, int, int, int]
    interpolation: bool = True


def parse_bits_list(value: str, expected: int, label: str) -> Tuple[int, ...]:
    parts = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if len(parts) != expected:
        raise ValueError(f"{label} must contain {expected} comma-separated integers")
    if any(bit < 1 or bit > 8 for bit in parts):
        raise ValueError(f"{label} values must be in 1..8")
    return parts


def parse_branch_bits(value: str) -> Dict[str, int]:
    parts = parse_bits_list(value, len(BRANCHES), "branch bits")
    return dict(zip(BRANCHES, parts))


def dataset_entries(names: Sequence[str]) -> List[Tuple[str, str]]:
    aliases = {display.lower(): (display, folder) for display, folder in DEFAULT_DATASETS}
    aliases.update({folder.lower(): (display, folder) for display, folder in DEFAULT_DATASETS})
    entries = []
    for name in names:
        key = name.lower()
        if key not in aliases:
            raise ValueError(f"unknown dataset {name!r}")
        entries.append(aliases[key])
    return entries


def calculate_psnr(img1: np.ndarray, img2: np.ndarray, data_range: float = 255.0) -> float:
    diff = img1.astype(np.float32) - img2.astype(np.float32)
    mse = np.mean(diff * diff)
    if mse == 0:
        return float("inf")
    return 10 * math.log10((data_range * data_range) / float(mse))


def shave_boundary(image: np.ndarray, shave_size: int) -> np.ndarray:
    return image[shave_size:-shave_size, shave_size:-shave_size]


def modcrop_y(image_y: np.ndarray, scale: int) -> np.ndarray:
    h, w = image_y.shape
    return image_y[: h - (h % scale), : w - (w % scale)]


def downsample_y_bicubic(hr_y: np.ndarray, scale: int) -> np.ndarray:
    hr_img = Image.fromarray(hr_y, mode="L")
    lr_img = hr_img.resize((hr_y.shape[1] // scale, hr_y.shape[0] // scale), Image.BICUBIC)
    return np.asarray(lr_img, dtype=np.uint8)


def find_dataset_dirs(base_dir: Path, folder_name: str) -> Tuple[Path, Path | None]:
    root = base_dir / folder_name / folder_name
    if (root / "GTmod12").is_dir():
        return root / "GTmod12", root / "LRbicx2"
    return root, None


def image_files(directory: Path) -> List[Path]:
    return sorted(path for path in directory.iterdir() if path.suffix.lower() in VALID_EXTS)


def quantize_signed_msb(values: np.ndarray, bits: Sequence[int]) -> np.ndarray:
    """Keep MSBs of signed int8-like values and reconstruct to int16 values.

    This models storing fewer output bits while keeping the original signed int8
    dynamic range. For example, 6-bit output keeps the signed magnitude at a
    4-value step after reconstruction.
    """
    bits_arr = np.asarray(bits, dtype=np.int16).reshape(1, 1, LUT_ENTRY_WIDTH)
    drops = 8 - bits_arr
    scale = (1 << drops).astype(np.int16)
    rounded = np.rint(values.astype(np.float32) / scale).astype(np.int16) * scale
    return np.clip(rounded, -128, 127).astype(np.int16)


def estimate_lut_bytes(config: CompressionConfig) -> int:
    word_bits = sum(config.channel_bits)
    total_bits = 0
    for branch in BRANCHES:
        depth = 1 << (3 * config.branch_input_bits[branch])
        total_bits += depth * word_bits
    return (total_bits + 7) // 8


def format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MiB"
    return f"{num_bytes / 1024:.2f} KiB"


class CompressedLUTSimulator:
    def __init__(self, full_lut_dir: Path, config: CompressionConfig):
        self.full_luts = PIMSRLUTSet.from_dir(full_lut_dir).luts
        self.config = config

    def simulate_features(self, image_y: np.ndarray) -> np.ndarray:
        acc = None
        for branch in BRANCHES:
            bits = self.config.branch_input_bits[branch]
            values = self._branch_interpolated_values(image_y, branch, bits)
            values = quantize_signed_msb(values, self.config.channel_bits)
            acc = values if acc is None else acc + values
        return np.clip(acc, 0, 255).astype(np.uint8)

    def simulate_image(self, image_y: np.ndarray) -> np.ndarray:
        return pixel_shuffle_x2(self.simulate_features(image_y))

    def _branch_interpolated_values(self, image_y: np.ndarray, branch: str, bits: int) -> np.ndarray:
        windows = branch_windows(image_y, branch)
        if bits == 8:
            addr = address_from_pixels(windows[:, :, 0], windows[:, :, 1], windows[:, :, 2])
            return self.full_luts[branch][addr].astype(np.int16)

        if not self.config.interpolation:
            shift = 8 - bits
            q = (windows.astype(np.uint16) >> shift) << shift
            addr = address_from_pixels(q[:, :, 0], q[:, :, 1], q[:, :, 2])
            return self.full_luts[branch][addr].astype(np.int16)

        return self._tetrahedral_interpolate(branch, windows, bits)

    def _tetrahedral_interpolate(self, branch: str, windows: np.ndarray, bits: int) -> np.ndarray:
        shift = 8 - bits
        max_index = (1 << bits) - 1
        idx = windows.astype(np.uint16) >> shift
        frac = (windows.astype(np.float32) - ((idx << shift).astype(np.float32))) / float(1 << shift)

        upper_idx = np.minimum(idx + 1, max_index)
        at_upper_edge = idx == max_index
        frac = np.where(at_upper_edge, 0.0, frac)

        low_level = (idx << shift).astype(np.uint8)
        high_level = (upper_idx << shift).astype(np.uint8)

        v000 = self._vertex(branch, low_level, high_level, (0, 0, 0))
        v100 = self._vertex(branch, low_level, high_level, (1, 0, 0))
        v010 = self._vertex(branch, low_level, high_level, (0, 1, 0))
        v001 = self._vertex(branch, low_level, high_level, (0, 0, 1))
        v110 = self._vertex(branch, low_level, high_level, (1, 1, 0))
        v101 = self._vertex(branch, low_level, high_level, (1, 0, 1))
        v011 = self._vertex(branch, low_level, high_level, (0, 1, 1))
        v111 = self._vertex(branch, low_level, high_level, (1, 1, 1))

        x = frac[:, :, 0]
        y = frac[:, :, 1]
        z = frac[:, :, 2]
        out = np.empty_like(v000, dtype=np.float32)

        def apply(mask, first, second, third, w1, w2, w3):
            value = (
                v000.astype(np.float32)
                + w1[:, :, None] * (first.astype(np.float32) - v000.astype(np.float32))
                + w2[:, :, None] * (second.astype(np.float32) - first.astype(np.float32))
                + w3[:, :, None] * (third.astype(np.float32) - second.astype(np.float32))
            )
            out[mask] = value[mask]

        apply((x >= y) & (y >= z), v100, v110, v111, x, y, z)
        apply((x >= z) & (z > y), v100, v101, v111, x, z, y)
        apply((y > x) & (x >= z), v010, v110, v111, y, x, z)
        apply((y >= z) & (z > x), v010, v011, v111, y, z, x)
        apply((z > x) & (x >= y), v001, v101, v111, z, x, y)
        apply((z > y) & (y > x), v001, v011, v111, z, y, x)

        return np.clip(np.rint(out), -128, 127).astype(np.int16)

    def _vertex(
        self,
        branch: str,
        low_level: np.ndarray,
        high_level: np.ndarray,
        selector: Tuple[int, int, int],
    ) -> np.ndarray:
        p = [high_level[:, :, axis] if selector[axis] else low_level[:, :, axis] for axis in range(3)]
        addr = address_from_pixels(p[0], p[1], p[2])
        return self.full_luts[branch][addr].astype(np.int16)


def evaluate_image(simulator: CompressedLUTSimulator, hr_path: Path, lr_path: Path | None, scale: int):
    hr_y = modcrop_y(load_y_image(hr_path), scale)
    if lr_path is not None and lr_path.exists():
        lr_y = load_y_image(lr_path)
    else:
        lr_y = downsample_y_bicubic(hr_y, scale)

    sr_orig = simulator.simulate_image(lr_y).astype(np.float32)
    sr_hflip = simulator.simulate_image(np.fliplr(lr_y).copy()).astype(np.float32)
    sr_hflip_back = np.fliplr(sr_hflip)
    sr_y = np.clip(np.rint((sr_orig + sr_hflip_back) / 2.0), 0, 255).astype(np.uint8)

    hr_y = hr_y[: sr_y.shape[0], : sr_y.shape[1]]
    sr_shaved = shave_boundary(sr_y, scale)
    hr_shaved = shave_boundary(hr_y, scale)

    psnr = calculate_psnr(sr_shaved, hr_shaved)
    ssim = calculate_ssim(
        hr_shaved.astype(np.float32),
        sr_shaved.astype(np.float32),
        data_range=255.0,
    )
    return psnr, ssim


def evaluate_config(
    config: CompressionConfig,
    base_dir: Path,
    lut_dir: Path,
    datasets: Sequence[Tuple[str, str]],
    scale: int,
) -> Dict[str, Tuple[float, float]]:
    simulator = CompressedLUTSimulator(lut_dir, config)
    results = {}
    print(
        f"\n[{config.name}] estimated LUT storage: "
        f"{format_size(estimate_lut_bytes(config))}"
    )
    print(f"  branch input bits: {dict(config.branch_input_bits)}")
    print(f"  channel bits: {config.channel_bits}")

    for display_name, folder_name in datasets:
        hr_dir, lr_dir = find_dataset_dirs(base_dir, folder_name)
        files = image_files(hr_dir)
        psnr_list = []
        ssim_list = []
        print(f"  {display_name:<10s} ({len(files):3d}) ...", flush=True)

        for hr_path in files:
            lr_path = None
            if lr_dir is not None:
                candidate = lr_dir / hr_path.name
                if candidate.exists():
                    lr_path = candidate
            psnr, ssim = evaluate_image(simulator, hr_path, lr_path, scale)
            psnr_list.append(psnr)
            ssim_list.append(ssim)

        results[display_name] = (
            sum(psnr_list) / len(psnr_list),
            sum(ssim_list) / len(ssim_list),
        )

    return results


def preset_configs() -> List[CompressionConfig]:
    return [
        CompressionConfig(
            name="method2_input4_interp",
            branch_input_bits={branch: 4 for branch in BRANCHES},
            channel_bits=(8, 8, 8, 8),
            interpolation=True,
        ),
        CompressionConfig(
            name="method2_input5_interp",
            branch_input_bits={branch: 5 for branch in BRANCHES},
            channel_bits=(8, 8, 8, 8),
            interpolation=True,
        ),
        CompressionConfig(
            name="method4_branch_4_4_3_3",
            branch_input_bits={"left": 4, "right": 4, "top": 3, "bot": 3},
            channel_bits=(8, 8, 8, 8),
            interpolation=True,
        ),
        CompressionConfig(
            name="method5_channel_8_8_6_6",
            branch_input_bits={branch: 4 for branch in BRANCHES},
            channel_bits=(8, 8, 6, 6),
            interpolation=True,
        ),
        CompressionConfig(
            name="method6_output6",
            branch_input_bits={branch: 4 for branch in BRANCHES},
            channel_bits=(6, 6, 6, 6),
            interpolation=True,
        ),
    ]


def print_summary(config_results: Sequence[Tuple[CompressionConfig, Dict[str, Tuple[float, float]]]]) -> None:
    print("\n" + "=" * 78)
    print("LUT Compression Evaluation Summary")
    print("=" * 78)
    for config, results in config_results:
        print(f"\n{config.name} ({format_size(estimate_lut_bytes(config))})")
        print(f"{'Dataset':<12s} | {'PSNR (dB)':<12s} | {'SSIM':<10s}")
        print("-" * 42)
        for display_name, _ in DEFAULT_DATASETS:
            if display_name in results:
                psnr, score = results[display_name]
                print(f"{display_name:<12s} | {psnr:<12.2f} | {score:<10.4f}")


def build_config_from_args(args) -> List[CompressionConfig]:
    if args.method == "presets":
        return preset_configs()

    if args.method == "method2":
        return [
            CompressionConfig(
                name=f"method2_input{args.input_bits}_interp",
                branch_input_bits={branch: args.input_bits for branch in BRANCHES},
                channel_bits=(8, 8, 8, 8),
                interpolation=True,
            )
        ]

    if args.method == "method4":
        branch_bits = parse_branch_bits(args.branch_bits)
        return [
            CompressionConfig(
                name=f"method4_branch_{'_'.join(str(branch_bits[b]) for b in BRANCHES)}",
                branch_input_bits=branch_bits,
                channel_bits=(8, 8, 8, 8),
                interpolation=True,
            )
        ]

    if args.method == "method5":
        channel_bits = parse_bits_list(args.channel_bits, LUT_ENTRY_WIDTH, "channel bits")
        return [
            CompressionConfig(
                name=f"method5_channel_{'_'.join(str(bit) for bit in channel_bits)}",
                branch_input_bits={branch: args.input_bits for branch in BRANCHES},
                channel_bits=channel_bits,
                interpolation=True,
            )
        ]

    if args.method == "method6":
        return [
            CompressionConfig(
                name=f"method6_output{args.output_bits}",
                branch_input_bits={branch: args.input_bits for branch in BRANCHES},
                channel_bits=(args.output_bits,) * LUT_ENTRY_WIDTH,
                interpolation=True,
            )
        ]

    raise ValueError(f"unsupported method {args.method!r}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate PIMSR LUT compression strategies using full LUTs as golden source."
    )
    parser.add_argument(
        "--method",
        choices=("method2", "method4", "method5", "method6", "presets"),
        default="presets",
        help=(
            "method2=sampled+tetrahedral, method4=per-branch input bits, "
            "method5=per-channel output bits, method6=uniform output bits"
        ),
    )
    parser.add_argument("--dataset-dir", type=Path, default=Path("dataset"))
    parser.add_argument("--lut-dir", type=Path, default=Path("lut_out"))
    parser.add_argument("--datasets", nargs="+", default=[name for name, _ in DEFAULT_DATASETS])
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--input-bits", type=int, default=4, help="input MSB count for method2/5/6")
    parser.add_argument(
        "--branch-bits",
        default="4,4,3,3",
        help="method4 bits in left,right,top,bot order",
    )
    parser.add_argument(
        "--channel-bits",
        default="8,8,6,6",
        help="method5 bits in TL,TR,BL,BR order",
    )
    parser.add_argument("--output-bits", type=int, default=6, help="method6 uniform output bit count")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    configs = build_config_from_args(args)
    datasets = dataset_entries(args.datasets)

    all_results = []
    for config in configs:
        results = evaluate_config(config, args.dataset_dir, args.lut_dir, datasets, args.scale)
        all_results.append((config, results))

    print_summary(all_results)


if __name__ == "__main__":
    main()
