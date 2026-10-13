"""PIMSR LUT export, simulation, and hardware trace tools.

The LUT contract follows the current PIMSR_Net in model.py:

* Four branches: left, right, top, bot.
* Each branch address is three 8-bit Y pixels:
  addr = (p0 << 16) | (p1 << 8) | p2.
* Each LUT entry stores four int8 values in PyTorch PixelShuffle(2)
  channel order: TL, TR, BL, BR.
* Runtime sums four branch entries, clamps to 0..255, then pixel-shuffles.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, Mapping, Optional, Sequence, Tuple

import numpy as np
from PIL import Image


BRANCHES: Tuple[str, ...] = ("left", "right", "top", "bot")
LUT_ENTRY_WIDTH = 4
FULL_LUT_DEPTH = 256**3


@dataclass(frozen=True)
class BranchSpec:
    name: str
    orientation: str
    offsets: Tuple[int, int, int]
    center_index: int


BRANCH_SPECS: Mapping[str, BranchSpec] = {
    "left": BranchSpec("left", "h", (-2, -1, 0), 2),
    "right": BranchSpec("right", "h", (0, 1, 2), 0),
    "top": BranchSpec("top", "v", (-2, -1, 0), 2),
    "bot": BranchSpec("bot", "v", (0, 1, 2), 0),
}


def address_from_pixels(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """Pack three uint8 pixel arrays into the shared 24-bit LUT address."""
    return (
        (p0.astype(np.uint32) << 16)
        | (p1.astype(np.uint32) << 8)
        | p2.astype(np.uint32)
    )


def unpack_address(address: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    addr = np.asarray(address, dtype=np.uint32)
    return (
        ((addr >> 16) & 0xFF).astype(np.uint8),
        ((addr >> 8) & 0xFF).astype(np.uint8),
        (addr & 0xFF).astype(np.uint8),
    )


def quantize_signed_int8(values: np.ndarray) -> np.ndarray:
    """Match torch.round + signed int8 clamp used by QmnQuantizer(frac_bits=0)."""
    return np.clip(np.rint(values), -128, 127).astype(np.int8)


def clamp_uint8_feature(values: np.ndarray) -> np.ndarray:
    return np.clip(values, 0, 255).astype(np.uint8)


def pixel_shuffle_x2(features: np.ndarray) -> np.ndarray:
    """Convert HxWx4 features to a 2H x 2W image using PyTorch channel order."""
    if features.ndim != 3 or features.shape[2] != LUT_ENTRY_WIDTH:
        raise ValueError("features must have shape HxWx4")

    h, w, _ = features.shape
    out = np.empty((h * 2, w * 2), dtype=features.dtype)
    out[0::2, 0::2] = features[:, :, 0]
    out[0::2, 1::2] = features[:, :, 1]
    out[1::2, 0::2] = features[:, :, 2]
    out[1::2, 1::2] = features[:, :, 3]
    return out


def load_y_image(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("YCbCr").split()[0], dtype=np.uint8)


def save_y_image(path: Path, image: np.ndarray) -> None:
    Image.fromarray(np.asarray(image, dtype=np.uint8), mode="L").save(path)


def branch_windows(image_y: np.ndarray, branch: str) -> np.ndarray:
    """Return HxWx3 uint8 windows for one branch using replicate padding."""
    if branch not in BRANCH_SPECS:
        raise ValueError(f"unknown branch {branch!r}")
    if image_y.ndim != 2:
        raise ValueError("image_y must be a 2-D Y-channel array")

    spec = BRANCH_SPECS[branch]
    padded = np.pad(image_y, ((2, 2), (2, 2)), mode="edge")
    h, w = image_y.shape
    windows = np.empty((h, w, 3), dtype=np.uint8)

    if spec.orientation == "h":
        row = slice(2, 2 + h)
        for idx, offset in enumerate(spec.offsets):
            col_start = 2 + offset
            windows[:, :, idx] = padded[row, col_start : col_start + w]
    else:
        col = slice(2, 2 + w)
        for idx, offset in enumerate(spec.offsets):
            row_start = 2 + offset
            windows[:, :, idx] = padded[row_start : row_start + h, col]

    return windows


def branch_addresses(image_y: np.ndarray, branch: str) -> np.ndarray:
    windows = branch_windows(image_y, branch)
    return address_from_pixels(windows[:, :, 0], windows[:, :, 1], windows[:, :, 2])


def iter_address_batches(batch_size: int) -> Iterator[np.ndarray]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    for start in range(0, FULL_LUT_DEPTH, batch_size):
        stop = min(start + batch_size, FULL_LUT_DEPTH)
        yield np.arange(start, stop, dtype=np.uint32)


def load_lut_file(path: Path, mmap: bool = True) -> np.ndarray:
    mode = "r" if mmap else None
    lut = np.memmap(path, dtype=np.int8, mode=mode, shape=(FULL_LUT_DEPTH, LUT_ENTRY_WIDTH))
    if mmap:
        return lut
    return np.asarray(lut)


def write_mem_file(lut: np.ndarray, output_path: Path) -> None:
    """Write one 32-bit hex word per line for $readmemh/XPM initialization."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        for entry in lut:
            f.write("".join(f"{int(v) & 0xFF:02x}" for v in entry))
            f.write("\n")


def write_coe_file(lut: np.ndarray, output_path: Path) -> None:
    """Write a Vivado Block Memory Generator COE file with 32-bit words."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        f.write("memory_initialization_radix=16;\n")
        f.write("memory_initialization_vector=\n")
        last = len(lut) - 1
        for idx, entry in enumerate(lut):
            word = "".join(f"{int(v) & 0xFF:02x}" for v in entry)
            f.write(word)
            f.write(";\n" if idx == last else ",\n")


def convert_lut_file(input_path: Path, output_path: Path, fmt: str) -> None:
    lut = load_lut_file(input_path, mmap=True)
    if fmt == "mem":
        write_mem_file(lut, output_path)
    elif fmt == "coe":
        write_coe_file(lut, output_path)
    else:
        raise ValueError(f"unsupported format {fmt!r}")


class PIMSRLUTSet:
    def __init__(self, luts: Mapping[str, np.ndarray]):
        missing = [branch for branch in BRANCHES if branch not in luts]
        if missing:
            raise ValueError(f"missing LUT branches: {', '.join(missing)}")
        self.luts = dict(luts)
        for branch, lut in self.luts.items():
            if lut.shape != (FULL_LUT_DEPTH, LUT_ENTRY_WIDTH):
                raise ValueError(
                    f"{branch} LUT shape must be {(FULL_LUT_DEPTH, LUT_ENTRY_WIDTH)}, got {lut.shape}"
                )
            if lut.dtype != np.int8:
                raise ValueError(f"{branch} LUT dtype must be int8, got {lut.dtype}")

    @classmethod
    def from_dir(cls, lut_dir: Path, mmap: bool = True) -> "PIMSRLUTSet":
        return cls({branch: load_lut_file(lut_dir / f"{branch}.bin", mmap=mmap) for branch in BRANCHES})

    def simulate_features(self, image_y: np.ndarray) -> np.ndarray:
        acc: Optional[np.ndarray] = None
        for branch in BRANCHES:
            addr = branch_addresses(image_y, branch)
            values = self.luts[branch][addr].astype(np.int16)
            acc = values if acc is None else acc + values
        if acc is None:
            raise RuntimeError("no LUT branches were evaluated")
        return clamp_uint8_feature(acc)

    def simulate_image(self, image_y: np.ndarray) -> np.ndarray:
        return pixel_shuffle_x2(self.simulate_features(image_y))


def simulate_with_lut_dir(input_path: Path, lut_dir: Path, output_path: Path) -> None:
    image_y = load_y_image(input_path)
    sr_y = PIMSRLUTSet.from_dir(lut_dir).simulate_image(image_y)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_y_image(output_path, sr_y)


def write_trace(input_path: Path, lut_dir: Path, trace_path: Path) -> None:
    image_y = load_y_image(input_path)
    lut_set = PIMSRLUTSet.from_dir(lut_dir)
    features = lut_set.simulate_features(image_y)
    addrs = {branch: branch_addresses(image_y, branch) for branch in BRANCHES}

    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "row",
                "col",
                "addr_left",
                "addr_right",
                "addr_top",
                "addr_bot",
                "out_tl",
                "out_tr",
                "out_bl",
                "out_br",
            ]
        )
        h, w = image_y.shape
        for row in range(h):
            for col in range(w):
                writer.writerow(
                    [
                        row,
                        col,
                        int(addrs["left"][row, col]),
                        int(addrs["right"][row, col]),
                        int(addrs["top"][row, col]),
                        int(addrs["bot"][row, col]),
                        int(features[row, col, 0]),
                        int(features[row, col, 1]),
                        int(features[row, col, 2]),
                        int(features[row, col, 3]),
                    ]
                )


def _require_torch():
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required for LUT export and PyTorch comparison") from exc
    return torch


def _load_model(checkpoint: Path, device: str):
    torch = _require_torch()
    from model import PIMSR_Net

    model = PIMSR_Net(scale_factor=2).to(device)
    state = _load_checkpoint_state(torch, checkpoint, device)
    model.load_state_dict(state)
    model.eval()
    model.quantize_enabled = True
    return model


def _load_checkpoint_state(torch, checkpoint: Path, device: str):
    if checkpoint.exists():
        return torch.load(checkpoint, map_location=device)

    zip_path = Path("checkpoints_2.zip")
    inner_name = checkpoint.as_posix()
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            if inner_name in names:
                data = zf.read(inner_name)
                return torch.load(io.BytesIO(data), map_location=device)

    raise FileNotFoundError(
        f"checkpoint not found: {checkpoint}. Also checked {zip_path} for {inner_name}."
    )


def _branch_modules(model, branch: str):
    return getattr(model, f"conv_{branch}"), getattr(model, f"mlp_{branch}")


def export_branch_lut(
    model,
    branch: str,
    output_path: Path,
    batch_size: int,
    device: str,
    write_mem: bool = False,
) -> None:
    torch = _require_torch()
    spec = BRANCH_SPECS[branch]
    conv, mlp = _branch_modules(model, branch)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("wb") as bin_file:
        mem_file = None
        if write_mem:
            mem_file = output_path.with_suffix(".mem").open("w")
        try:
            with torch.no_grad():
                for addresses in iter_address_batches(batch_size):
                    p0, p1, p2 = unpack_address(addresses)
                    pixels = np.stack([p0, p1, p2], axis=1).astype(np.float32)

                    if spec.orientation == "h":
                        x_np = pixels.reshape(-1, 1, 1, 3)
                    else:
                        x_np = pixels.reshape(-1, 1, 3, 1)

                    x = torch.from_numpy(x_np).to(device)
                    y = mlp(conv(x)).reshape(-1, LUT_ENTRY_WIDTH)
                    center = torch.from_numpy(pixels[:, spec.center_index]).to(device).reshape(-1, 1)
                    y = torch.clamp(torch.round(y + center / 4.0), -128, 127)
                    entries = y.to(torch.int8).cpu().numpy()
                    bin_file.write(entries.tobytes(order="C"))

                    if mem_file is not None:
                        for entry in entries:
                            mem_file.write("".join(f"{int(v) & 0xFF:02x}" for v in entry))
                            mem_file.write("\n")
        finally:
            if mem_file is not None:
                mem_file.close()


def export_luts(
    checkpoint: Path,
    output_dir: Path,
    batch_size: int = 1 << 18,
    device: str = "cpu",
    branches: Sequence[str] = BRANCHES,
    write_mem: bool = False,
) -> None:
    model = _load_model(checkpoint, device)
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "checkpoint": str(checkpoint),
        "branches": list(branches),
        "address_order": "addr = (p0 << 16) | (p1 << 8) | p2",
        "entry_dtype": "int8",
        "entry_channels": ["top_left", "top_right", "bottom_left", "bottom_right"],
        "depth": FULL_LUT_DEPTH,
        "entry_width": LUT_ENTRY_WIDTH,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    for branch in branches:
        if branch not in BRANCHES:
            raise ValueError(f"unknown branch {branch!r}")
        export_branch_lut(
            model=model,
            branch=branch,
            output_path=output_dir / f"{branch}.bin",
            batch_size=batch_size,
            device=device,
            write_mem=write_mem,
        )


def compare_torch_to_lut(checkpoint: Path, lut_dir: Path, seed: int = 2026, size: int = 8) -> None:
    torch = _require_torch()
    model = _load_model(checkpoint, "cpu")
    rng = np.random.default_rng(seed)
    image_y = rng.integers(0, 256, size=(size, size), dtype=np.uint8)
    lut_out = PIMSRLUTSet.from_dir(lut_dir).simulate_image(image_y).astype(np.float32)

    x = torch.from_numpy(image_y.astype(np.float32)).reshape(1, 1, size, size)
    with torch.no_grad():
        torch_out = model(x).reshape(size * 2, size * 2).cpu().numpy()
        torch_out = np.clip(torch_out, 0, 255).astype(np.float32)

    diff = np.abs(torch_out - lut_out)
    print(f"max_abs_diff={diff.max():.6f}")
    print(f"num_mismatch={int(np.count_nonzero(diff))}")
    if np.count_nonzero(diff):
        raise SystemExit(1)


def selftest() -> None:
    p0 = np.array([0, 1, 255], dtype=np.uint8)
    p1 = np.array([2, 3, 128], dtype=np.uint8)
    p2 = np.array([4, 5, 64], dtype=np.uint8)
    addr = address_from_pixels(p0, p1, p2)
    up0, up1, up2 = unpack_address(addr)
    assert np.array_equal(p0, up0)
    assert np.array_equal(p1, up1)
    assert np.array_equal(p2, up2)

    image = np.array([[10, 20], [30, 40]], dtype=np.uint8)
    assert branch_windows(image, "left")[0, 0].tolist() == [10, 10, 10]
    assert branch_windows(image, "right")[0, 0].tolist() == [10, 20, 20]
    assert branch_windows(image, "top")[0, 0].tolist() == [10, 10, 10]
    assert branch_windows(image, "bot")[0, 0].tolist() == [10, 30, 30]

    features = np.array([[[1, 2, 3, 4]]], dtype=np.uint8)
    assert pixel_shuffle_x2(features).tolist() == [[1, 2], [3, 4]]

    q = quantize_signed_int8(np.array([-129.0, -128.0, -1.5, 0.5, 126.6, 128.0]))
    assert q.tolist() == [-128, -128, -2, 0, 127, 127]
    print("selftest passed")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PIMSR full 8-bit LUT tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    export_p = sub.add_parser("export", help="export four full 8-bit LUT binary files")
    export_p.add_argument("--checkpoint", type=Path, default=Path("checkpoints/pimsr_final_swa.pth"))
    export_p.add_argument("--output-dir", type=Path, default=Path("lut_out"))
    export_p.add_argument("--batch-size", type=int, default=1 << 18)
    export_p.add_argument("--device", default="cpu")
    export_p.add_argument("--branches", nargs="+", choices=BRANCHES, default=list(BRANCHES))
    export_p.add_argument("--write-mem", action="store_true", help="also emit text .mem files")

    sim_p = sub.add_parser("simulate", help="run LUT inference on an input image")
    sim_p.add_argument("--input", type=Path, required=True)
    sim_p.add_argument("--lut-dir", type=Path, required=True)
    sim_p.add_argument("--output", type=Path, required=True)

    trace_p = sub.add_parser("trace", help="write hardware address/output trace CSV")
    trace_p.add_argument("--input", type=Path, required=True)
    trace_p.add_argument("--lut-dir", type=Path, required=True)
    trace_p.add_argument("--output", type=Path, required=True)

    cmp_p = sub.add_parser("compare", help="compare random PyTorch output with LUT simulator")
    cmp_p.add_argument("--checkpoint", type=Path, default=Path("checkpoints/pimsr_final_swa.pth"))
    cmp_p.add_argument("--lut-dir", type=Path, required=True)
    cmp_p.add_argument("--seed", type=int, default=2026)
    cmp_p.add_argument("--size", type=int, default=8)

    conv_p = sub.add_parser("convert", help="convert one branch .bin LUT to .mem or .coe")
    conv_p.add_argument("--input", type=Path, required=True)
    conv_p.add_argument("--output", type=Path, required=True)
    conv_p.add_argument("--format", choices=("mem", "coe"), required=True)

    sub.add_parser("selftest", help="run dependency-light unit checks")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.cmd == "export":
        export_luts(
            checkpoint=args.checkpoint,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            device=args.device,
            branches=args.branches,
            write_mem=args.write_mem,
        )
    elif args.cmd == "simulate":
        simulate_with_lut_dir(args.input, args.lut_dir, args.output)
    elif args.cmd == "trace":
        write_trace(args.input, args.lut_dir, args.output)
    elif args.cmd == "compare":
        compare_torch_to_lut(args.checkpoint, args.lut_dir, seed=args.seed, size=args.size)
    elif args.cmd == "convert":
        convert_lut_file(args.input, args.output, args.format)
    elif args.cmd == "selftest":
        selftest()
    else:
        raise ValueError(f"unhandled command {args.cmd!r}")


if __name__ == "__main__":
    main()
