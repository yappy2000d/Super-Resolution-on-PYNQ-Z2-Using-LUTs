import os
import torch
import math
import numpy as np
from PIL import Image
from torchvision.transforms import functional as TF
from skimage.metrics import structural_similarity as calculate_ssim

from model import PIMSR_Net

def calculate_psnr(img1, img2, data_range=255.0):
    mse = torch.mean((img1 - img2) ** 2)
    if mse == 0:
        return float('inf')
    return 10 * math.log10((data_range ** 2) / mse.item())

def shave_boundary(tensor, shave_size):
    return tensor[:, :, shave_size:-shave_size, shave_size:-shave_size]

def evaluate_image(model, lr_image_path, hr_image_path, scale, device):
    # 讀取並只取 Y 通道
    lr_img = Image.open(lr_image_path).convert('YCbCr').split()[0]
    hr_img = Image.open(hr_image_path).convert('YCbCr').split()[0]

    lr_tensor = TF.to_tensor(lr_img).unsqueeze(0) * 255.0
    hr_tensor = TF.to_tensor(hr_img).unsqueeze(0) * 255.0
    lr_tensor, hr_tensor = lr_tensor.to(device), hr_tensor.to(device)

    with torch.no_grad():
        # 1. 原始影像推論
        sr_tensor_orig = model(lr_tensor)
        
        # # 2. 水平翻轉推論
        # lr_tensor_hflip = torch.flip(lr_tensor, [3])
        # sr_tensor_hflip = model(lr_tensor_hflip)
        # sr_tensor_hflip_back = torch.flip(sr_tensor_hflip, [3])
        
        # # 4. 兩者取平均
        # sr_tensor = (sr_tensor_orig + sr_tensor_hflip_back) / 2.0
        sr_tensor=sr_tensor_orig
        # 數值模擬：四捨五入與截斷
        sr_tensor = torch.clamp(torch.round(sr_tensor), 0.0, 255.0)

    # 邊緣裁切 (Shave)
    sr_tensor = shave_boundary(sr_tensor, scale)
    hr_tensor = shave_boundary(hr_tensor, scale)

    # 計算 PSNR & SSIM
    psnr_value = calculate_psnr(sr_tensor, hr_tensor)
    
    sr_np = sr_tensor.squeeze().cpu().numpy().astype(np.float32)
    hr_np = hr_tensor.squeeze().cpu().numpy().astype(np.float32)
    ssim_value = calculate_ssim(hr_np, sr_np, data_range=255.0)

    return psnr_value, ssim_value

if __name__ == '__main__':
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scale_factor = 2
    
    model = PIMSR_Net(scale_factor=scale_factor).to(device)
    # weight_path = "checkpoints/pimsr_epoch_3999.pth"
    weight_path = "checkpoints/pimsr_final_swa.pth"
    
    try:
        model.load_state_dict(torch.load(weight_path, map_location=device))
        model.eval() 
        model.quantize_enabled = True
    except FileNotFoundError:
        print(f"錯誤：找不到權重檔 {weight_path}")
        exit()
    
    benchmark_base_dir = "./datasets/benchmarks"
    datasets = ["Set5", "Set14", "BSDS100", "Urban100", "Manga109"]
    
    results = {}

    print(f"=== PIMSR 硬體模擬評估 (權重: {weight_path}) ===\n")

    # 3. 逐一進入各個 Benchmark 資料夾
    for dataset_name in datasets:
        print(f"正在評估: {dataset_name}", flush=True, end="")
        
        test_lr_dir = os.path.join(benchmark_base_dir, dataset_name, "X")
        test_hr_dir = os.path.join(benchmark_base_dir, dataset_name, "Y")
        
        if not os.path.exists(test_lr_dir) or not os.path.exists(test_hr_dir):
            print(f" [跳過] 找不到 X 或 Y 資料夾。")
            continue
            
        valid_exts = ('.png', '.jpg', '.jpeg', '.bmp')
        hr_filenames = [f for f in os.listdir(test_hr_dir) if f.lower().endswith(valid_exts)]
        print(f"({len(hr_filenames)}) ...", end="")
        
        psnr_list, ssim_list = [], []
        
        for hr_name in hr_filenames:
            name, ext = os.path.splitext(hr_name)
            lr_name = f"{name}x{scale_factor}{ext}" 
            
            lr_path = os.path.join(test_lr_dir, lr_name)
            hr_path = os.path.join(test_hr_dir, hr_name)
            
            if os.path.exists(lr_path):
                psnr, ssim = evaluate_image(model, lr_path, hr_path, scale_factor, device)
                psnr_list.append(psnr)
                ssim_list.append(ssim)
                
        # 計算該資料集的平均
        if psnr_list:
            avg_psnr = sum(psnr_list) / len(psnr_list)
            avg_ssim = sum(ssim_list) / len(ssim_list)
            results[dataset_name] = (avg_psnr, avg_ssim)
            print(f" 完成！")
        else:
            print(f" [失敗] 沒有可計算的圖片。")

    print("\n" + "="*45)
    print(" 最終個別資料集評估報告 (Y-Channel Only)")
    print("="*45)
    print(f"{'Dataset':<12s} | {'PSNR (dB)':<12s} | {'SSIM':<10s}")
    print("-" * 45)
    
    for dataset_name in datasets:
        if dataset_name in results:
            psnr, ssim = results[dataset_name]
            print(f"{dataset_name:<12s} | {psnr:<12.2f} | {ssim:<10.4f}")
        else:
            print(f"{dataset_name:<12s} | {'N/A':<12.2f} | {'N/A':<10.4f}")
            
    print("="*45)