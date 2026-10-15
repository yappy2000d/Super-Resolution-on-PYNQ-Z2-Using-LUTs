"""x2 SR benchmark: Bicubic vs. float PyTorch vs. QAT int8 PyTorch vs. Verilog (ModelSim simulation).

Y-channel only (PIL YCbCr, same as eval_all.py), shave = scale = 2 px, PSNR averaged per image.
The "Verilog" column comes from running the project's own RTL (pynq/PL/vivado/rtl/*.v, unmodified,
top = pimsr_image_core via tb/tb_pimsr_image_core_bench.v) in ModelSim, one vsim process per image.
Only the parameters IMG_W / IMG_H / LR_ADDR_WIDTH / HR_ADDR_WIDTH are overridden per image.
A vectorised numpy copy of the datapath (`lut_sr`) is kept as a cross-check: the script reports
whether every simulated HR image is bit-identical to it. `--selfcheck` compares that numpy copy with
the scalar golden model used for the RTL testbenches (tb/gen_pixel_core_vectors.py).

  python eval_benchmarks.py --data torch/datasets/_raw --datasets Set5 Set14 BSD100 Urban100
"""
import argparse
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "torch"))
sys.path.insert(0, str(ROOT.parent / "pynq" / "PL" / "vivado" / "tb"))
from model import PIMSR_Net  # noqa: E402
import gen_pixel_core_vectors as golden  # noqa: E402

BRANCHES = golden.BRANCHES  # left, right, top, bot
SCALE = 2


def load_y(path):
    return np.asarray(Image.open(path).convert("YCbCr").split()[0], dtype=np.uint8)


def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * math.log10(255.0 ** 2 / mse)


def shave(a, s=SCALE):
    return a[s:-s, s:-s]


# ---------------------------------------------------------------- Verilog-equivalent LUT path
def load_lut(path):
    words = golden.read_mem(Path(path))  # 4096 x u32, [31:24]=TL ... [7:0]=BR
    w = np.array(words, dtype=np.uint32)
    ch = np.stack([(w >> s) & 0xFF for s in (24, 16, 8, 0)], axis=-1).astype(np.int32)
    ch = np.where(ch >= 128, ch - 256, ch)
    return ch.reshape(16, 16, 16, 4)  # indexed [i0, i1, i2, channel]


def interp_branch(lut, p0, p1, p2):
    """Vectorised golden.interp_branch. p*: int arrays (N,). Returns (N,4) int32 in [-128,127]."""
    p0, p1, p2 = (p.astype(np.int32) for p in (p0, p1, p2))
    i0, i1, i2 = p0 >> 4, p1 >> 4, p2 >> 4
    h0, h1, h2 = (np.minimum(i + 1, 15) for i in (i0, i1, i2))  # i==15 -> 15
    f0 = np.where(i0 == 15, 0, p0 & 15)
    f1 = np.where(i1 == 15, 0, p1 & 15)
    f2 = np.where(i2 == 15, 0, p2 & 15)

    v000, v100, v010, v001 = lut[i0, i1, i2], lut[h0, i1, i2], lut[i0, h1, i2], lut[i0, i1, h2]
    v110, v101, v011, v111 = lut[h0, h1, i2], lut[h0, i1, h2], lut[i0, h1, h2], lut[h0, h1, h2]

    c1 = (f0 >= f1) & (f1 >= f2)
    c2 = ~c1 & (f0 >= f2) & (f2 > f1)
    c3 = ~c1 & ~c2 & (f1 > f0) & (f0 >= f2)
    c4 = ~c1 & ~c2 & ~c3 & (f1 >= f2) & (f2 > f0)
    c5 = ~c1 & ~c2 & ~c3 & ~c4 & (f2 > f0) & (f0 >= f1)
    conds = [c1, c2, c3, c4, c5]  # else -> case 6

    def sel(opts):
        return np.select([c[:, None] if opts[0].ndim == 2 else c for c in conds], opts[:5], opts[5])

    first = sel([v100, v100, v010, v010, v001, v001])
    second = sel([v110, v101, v110, v011, v101, v011])
    w1 = sel([f0, f0, f1, f1, f2, f2])
    w2 = sel([f1, f2, f0, f2, f0, f1])
    w3 = sel([f2, f1, f2, f0, f1, f0])

    def rs4(v):  # round_shift4, arithmetic shift
        return np.where(v >= 0, (v + 8) >> 4, (v - 8) >> 4)

    acc = (v000
           + rs4(w1[:, None] * (first - v000))
           + rs4(w2[:, None] * (second - first))
           + rs4(w3[:, None] * (v111 - second)))
    return np.clip(acc, -128, 127)


def lut_sr(luts, lr_y):
    """Run the image core on a whole LR Y image -> HR Y (uint8)."""
    h, w = lr_y.shape
    pad = np.pad(lr_y, 2, mode="edge").astype(np.int32)  # == clamp_coord in pimsr_image_core.v
    c = pad[2:-2, 2:-2]
    win = {
        "left": (pad[2:-2, 0:-4], pad[2:-2, 1:-3], c),
        "right": (c, pad[2:-2, 3:-1], pad[2:-2, 4:]),
        "top": (pad[0:-4, 2:-2], pad[1:-3, 2:-2], c),
        "bot": (c, pad[3:-1, 2:-2], pad[4:, 2:-2]),
    }
    total = 0
    for b in BRANCHES:
        p0, p1, p2 = (a.reshape(-1) for a in win[b])
        total = total + interp_branch(luts[b], p0, p1, p2)
    out = np.clip(total, 0, 255).astype(np.uint8).reshape(h, w, 2, 2)  # [..., (TL,TR),(BL,BR)]
    return out.transpose(0, 2, 1, 3).reshape(h * 2, w * 2)


def selfcheck(luts, lut_dir, n=3000):
    scalar = {b: golden.read_mem(Path(lut_dir) / f"{b}_4bit.mem") for b in BRANCHES}
    rng = random.Random(1)
    # include saturated / edge nibbles
    pts = [[rng.choice([0, 15, 16, 240, 255, rng.randrange(256)]) for _ in range(3)] for _ in range(n)]
    pts += [[rng.randrange(256) for _ in range(3)] for _ in range(n)]
    a = np.array(pts)
    bad = 0
    for bi, b in enumerate(BRANCHES):
        got = interp_branch(luts[b], a[:, 0], a[:, 1], a[:, 2])
        for k, (p0, p1, p2) in enumerate(pts):
            if list(got[k]) != golden.interp_branch(scalar[b], p0, p1, p2):
                bad += 1
    print(f"selfcheck vs scalar golden (RTL-validated model): {len(pts) * 4} branch evaluations, mismatches = {bad}")

    # whole-image check against the shipped image-core golden vectors (4x4 -> 8x8)
    tb = ROOT.parent / "pynq" / "PL" / "vivado" / "tb"
    lr = np.array([int(x, 16) for x in (tb / "image_core_lr_4x4.mem").read_text().split()], dtype=np.uint8).reshape(4, 4)
    hr = np.array([int(x, 16) for x in (tb / "image_core_hr_8x8.mem").read_text().split()], dtype=np.uint8).reshape(8, 8)
    print("image-core shipped vectors identical:", bool(np.array_equal(lut_sr(luts, lr), hr)))
    return bad == 0


# ---------------------------------------------------------------- RTL simulation (ModelSim)
RTL_DIR = ROOT.parent / "pynq" / "PL" / "vivado"


def build_sim(sim_dir):
    lib = Path(sim_dir) / "build"
    shutil.rmtree(lib, ignore_errors=True)
    lib.mkdir(parents=True)
    srcs = [str(p) for p in sorted((RTL_DIR / "rtl").glob("*.v"))] + [str(RTL_DIR / "tb" / "tb_pimsr_image_core_bench.v")]
    subprocess.run(["vlib", "work"], cwd=lib, check=True, capture_output=True)
    r = subprocess.run(["vlog", "-work", "work"] + srcs, cwd=lib, capture_output=True, text=True)
    if r.returncode != 0 or "Error" in r.stdout:
        sys.exit("vlog failed:\n" + r.stdout + r.stderr)
    return lib / "work"


def rtl_sr(lib, sim_dir, lut_dir, tag, lr_y):
    """Simulate pimsr_image_core on a whole LR Y image. Returns HR Y (uint8)."""
    h, w = lr_y.shape
    job = Path(sim_dir) / "jobs" / tag
    shutil.rmtree(job, ignore_errors=True)
    job.mkdir(parents=True)
    for b in BRANCHES:
        shutil.copy(Path(lut_dir) / f"{b}_4bit.mem", job)
    (job / "lr.mem").write_bytes(("\n".join(f"{v:02x}" for v in lr_y.reshape(-1)) + "\n").encode())
    lr_bits = max(16, (h * w).bit_length())
    hr_bits = max(18, (4 * h * w).bit_length())
    cmd = ["vsim", "-c", "-lib", str(lib), f"-GIMG_W={w}", f"-GIMG_H={h}",
           f"-GLR_ADDR_WIDTH={lr_bits}", f"-GHR_ADDR_WIDTH={hr_bits}",
           "tb_pimsr_image_core_bench", "+LR=lr.mem", "+HR=hr.txt", "-do", "run -all; quit -f"]
    r = subprocess.run(cmd, cwd=job, capture_output=True, text=True)
    if "DONE:" not in r.stdout:
        sys.exit(f"RTL simulation failed for {tag}:\n{r.stdout[-1500:]}")
    hr = np.frombuffer(bytes.fromhex("".join((job / "hr.txt").read_text().split())), dtype=np.uint8)
    shutil.rmtree(job, ignore_errors=True)
    return hr.reshape(h * 2, w * 2)


# ---------------------------------------------------------------- PyTorch paths
@torch.no_grad()
def torch_sr(net, lr_y, quant):
    net.quantize_enabled = quant
    x = torch.from_numpy(lr_y.astype(np.float32))[None, None]
    y = net(x)[0, 0]
    return torch.clamp(torch.round(y), 0, 255).numpy().astype(np.uint8)


def bicubic_sr(lr_y):
    h, w = lr_y.shape
    return np.asarray(Image.fromarray(lr_y).resize((w * 2, h * 2), Image.BICUBIC), dtype=np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "torch" / "datasets" / "_raw")
    ap.add_argument("--datasets", nargs="+", default=["Set5", "Set14", "BSD100", "Urban100"])
    ap.add_argument("--checkpoint", type=Path, default=ROOT / "torch" / "checkpoints" / "pimsr_final_swa.pth")
    ap.add_argument("--lut-dir", type=Path, default=RTL_DIR / "lut_sampled_4bit")
    ap.add_argument("--limit", type=int, default=0, help="only first N images per dataset (debug)")
    ap.add_argument("--sim-jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2), help="parallel vsim processes")
    ap.add_argument("--sim-dir", type=Path, default=Path(tempfile.gettempdir()) / "pimsr_sim")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    torch.set_grad_enabled(False)
    torch.set_num_threads(2)
    net = PIMSR_Net(scale_factor=SCALE)
    net.load_state_dict(torch.load(args.checkpoint, map_location="cpu"))
    net.eval()
    luts = {b: load_lut(args.lut_dir / f"{b}_4bit.mem") for b in BRANCHES}
    if args.selfcheck and not selfcheck(luts, args.lut_dir):
        sys.exit("self-check failed")

    # gather images
    items = []  # (dataset, name, hr_y, lr_y)
    for ds in args.datasets:
        hr_dir = args.data / ds / "HR" / f"{ds}_HR"
        lr_dir = args.data / ds / "LR_x2" / f"{ds}_LR_x2"
        files = sorted(hr_dir.glob("*.png"))
        if args.limit:
            files = files[: args.limit]
        for hp in files:
            lp = next(lr_dir.glob(hp.stem + "*"))  # e.g. img_001x2.png / baby.png
            hr = load_y(hp)
            hr = hr[: hr.shape[0] // 2 * 2, : hr.shape[1] // 2 * 2]
            lr = load_y(lp)
            assert lr.shape == (hr.shape[0] // 2, hr.shape[1] // 2), (hp.name, lr.shape, hr.shape)
            items.append((ds, hp.stem, hr, lr))

    # RTL simulations start in the background, largest images first
    lib = build_sim(args.sim_dir)
    pool = ThreadPoolExecutor(max_workers=args.sim_jobs)
    futures = {}
    for k in sorted(range(len(items)), key=lambda k: -items[k][3].size):
        ds, name, _, lr = items[k]
        futures[k] = pool.submit(rtl_sr, lib, args.sim_dir, args.lut_dir, f"{ds}_{name}", lr)
    print(f"{len(items)} images, {sum(i[3].size for i in items) / 1e6:.1f} M LR pixels -> "
          f"ModelSim x{args.sim_jobs} (~87 cycles/pixel)", flush=True)

    methods = ["Bicubic", "Float (PyTorch)", "QAT int8 (PyTorch)", "Verilog (RTL sim)"]
    scores = {ds: {m: [] for m in methods} for ds in args.datasets}
    mismatch_imgs = []
    per_image = []
    for n, (ds, name, hr, lr) in enumerate(items, 1):
        sr = {"Bicubic": bicubic_sr(lr), "Float (PyTorch)": torch_sr(net, lr, False),
              "QAT int8 (PyTorch)": torch_sr(net, lr, True), "Verilog (RTL sim)": futures[n - 1].result()}
        if not np.array_equal(sr["Verilog (RTL sim)"], lut_sr(luts, lr)):
            mismatch_imgs.append(f"{ds}/{name}")
        row = {m: psnr(shave(o), shave(hr)) for m, o in sr.items()}
        for m in methods:
            scores[ds][m].append(row[m])
        per_image.append((ds, name, row))
        print(f"\r[{n}/{len(items)}] {ds}/{name}                    ", end="", flush=True)
    pool.shutdown()
    print()

    print("\nx2 SR, Y-channel PSNR (dB), shave 2, mean over images")
    head = f"{'Dataset':<10}{'#':>5}" + "".join(f"{m:>22}" for m in methods)
    print(head)
    print("-" * len(head))
    for ds in args.datasets:
        print(f"{ds:<10}{len(scores[ds][methods[0]]):>5}" + "".join(f"{np.mean(scores[ds][m]):>22.2f}" for m in methods))
    print(f"\nRTL sim vs numpy datapath model: {len(items) - len(mismatch_imgs)}/{len(items)} images bit-identical"
          + (f"; differing: {mismatch_imgs}" if mismatch_imgs else ""))
    out = ROOT / "benchmark_per_image.csv"
    with out.open("w", encoding="utf-8") as f:
        f.write("dataset,image," + ",".join(methods) + "\n")
        for ds, name, row in per_image:
            f.write(f"{ds},{name}," + ",".join(f"{row[m]:.4f}" for m in methods) + "\n")
    print("per-image PSNR written to", out)


if __name__ == "__main__":
    main()
