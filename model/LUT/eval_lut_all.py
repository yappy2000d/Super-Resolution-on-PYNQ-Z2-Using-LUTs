import math
import os
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as calculate_ssim

from pimsr_lut import PIMSRLUTSet, load_y_image


VALID_EXTS = (".png", ".jpg", ".jpeg", ".bmp")
DATASETS = [
    ("Set5", "Set5"),
    ("Set14", "Set14"),
    ("BSDS100", "BSDS100"),
    ("Urban100", "urban100"),
    ("Manga109", "manga109"),
]


def calculate_psnr(img1, img2, data_range=255.0):
    diff = img1.astype(np.float32) - img2.astype(np.float32)
    mse = np.mean(diff * diff)
    if mse == 0:
        return float("inf")
    return 10 * math.log10((data_range * data_range) / float(mse))


def shave_boundary(image, shave_size):
    return image[shave_size:-shave_size, shave_size:-shave_size]


def modcrop_y(image_y, scale):
    h, w = image_y.shape
    return image_y[: h - (h % scale), : w - (w % scale)]


def downsample_y_bicubic(hr_y, scale):
    hr_img = Image.fromarray(hr_y, mode="L")
    lr_img = hr_img.resize((hr_y.shape[1] // scale, hr_y.shape[0] // scale), Image.BICUBIC)
    return np.asarray(lr_img, dtype=np.uint8)


def find_dataset_dirs(base_dir, folder_name):
    root = base_dir / folder_name / folder_name
    if (root / "GTmod12").is_dir():
        return root / "GTmod12", root / "LRbicx2"
    return root, None


def image_files(directory):
    return sorted(path for path in directory.iterdir() if path.suffix.lower() in VALID_EXTS)


def evaluate_image(lut_set, hr_path, lr_path, scale):
    hr_y = modcrop_y(load_y_image(hr_path), scale)
    if lr_path is not None and lr_path.exists():
        lr_y = load_y_image(lr_path)
    else:
        lr_y = downsample_y_bicubic(hr_y, scale)

    sr_orig = lut_set.simulate_image(lr_y).astype(np.float32)
    sr_hflip = lut_set.simulate_image(np.fliplr(lr_y).copy()).astype(np.float32)
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


def evaluate_dataset(lut_set, base_dir, display_name, folder_name, scale):
    hr_dir, lr_dir = find_dataset_dirs(base_dir, folder_name)
    if not hr_dir.is_dir():
        print(f"{display_name}: missing HR dir {hr_dir}")
        return None

    files = image_files(hr_dir)
    psnr_list = []
    ssim_list = []
    print(f"{display_name:<10s} ({len(files):3d}) ...", flush=True)

    for hr_path in files:
        lr_path = None
        if lr_dir is not None:
            candidate = lr_dir / hr_path.name
            if candidate.exists():
                lr_path = candidate
        psnr, ssim = evaluate_image(lut_set, hr_path, lr_path, scale)
        psnr_list.append(psnr)
        ssim_list.append(ssim)

    return sum(psnr_list) / len(psnr_list), sum(ssim_list) / len(ssim_list)


def main():
    base_dir = Path("dataset")
    lut_dir = Path("lut_out")
    scale = 2

    lut_set = PIMSRLUTSet.from_dir(lut_dir)
    results = {}

    print("=== PIMSR LUT 評估 (Y-Channel Only) ===")
    print(f"LUT dir: {lut_dir.resolve()}")
    print(f"Dataset dir: {base_dir.resolve()}")
    print()

    for display_name, folder_name in DATASETS:
        result = evaluate_dataset(lut_set, base_dir, display_name, folder_name, scale)
        if result is not None:
            results[display_name] = result

    print("\n" + "=" * 45)
    print(" 最終 LUT 個別資料集評估報告 (Y-Channel Only)")
    print("=" * 45)
    print(f"{'Dataset':<12s} | {'PSNR (dB)':<12s} | {'SSIM':<10s}")
    print("-" * 45)

    for display_name, _ in DATASETS:
        if display_name in results:
            psnr, ssim = results[display_name]
            print(f"{display_name:<12s} | {psnr:<12.2f} | {ssim:<10.4f}")
        else:
            print(f"{display_name:<12s} | {'N/A':<12s} | {'N/A':<10s}")
    print("=" * 45)


if __name__ == "__main__":
    main()
