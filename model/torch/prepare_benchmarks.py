import os
from PIL import Image

def prepare_benchmarks(base_dir, datasets, scale=2):
    print(f"=== 啟動測試集 Bicubic 下採樣 (Scale x{scale}) ===\n")
    
    for dataset in datasets:
        print(f"正在處理資料集: {dataset} ...")
        y_dir = os.path.join(base_dir, dataset, "Y")
        x_dir = os.path.join(base_dir, dataset, "X")
        
        # 建立對應的 X 資料夾
        os.makedirs(x_dir, exist_ok=True)
        
        if not os.path.exists(y_dir):
            print(f"  [警告] 找不到目錄 {y_dir}，已跳過。")
            continue
            
        valid_exts = ('.png', '.jpg', '.jpeg', '.bmp')
        image_files = [f for f in os.listdir(y_dir) if f.lower().endswith(valid_exts)]
        
        if not image_files:
            print(f"  [警告] {y_dir} 內沒有圖片！")
            continue
            
        for filename in image_files:
            y_path = os.path.join(y_dir, filename)
            hr_img = Image.open(y_path).convert('RGB')
            
            # 1. ModCrop: 確保原圖長寬能被放大倍率(scale)整除
            w, h = hr_img.size
            w_new = w - (w % scale)
            h_new = h - (h % scale)
            
            # 如果尺寸不符，裁切並「覆寫」Y 資料夾裡的原圖
            if w != w_new or h != h_new:
                hr_img = hr_img.crop((0, 0, w_new, h_new))
                hr_img.save(y_path)
                print(f"    [修正] {filename} 已裁切為 {w_new}x{h_new} 以對齊倍率")
                
            # 2. Bicubic 下採樣
            # PIL.Image.BICUBIC 是超解析度學界公認的標準降採樣演算法之一
            lr_img = hr_img.resize((w_new // scale, h_new // scale), resample=Image.BICUBIC)
            
            # 3. 儲存至 X 資料夾並加上 x2 後綴
            name, ext = os.path.splitext(filename)
            x_filename = f"{name}x{scale}{ext}"
            x_path = os.path.join(x_dir, x_filename)
            
            lr_img.save(x_path)
            
        print(f"  >> {dataset} 處理完成！LR 圖片已儲存至 {x_dir}\n")

if __name__ == '__main__':
    # 對應你的資料夾名稱
    benchmark_dir = "./datasets/benchmarks"
    dataset_list = ["Set5", "Set14", "BSDS100","manga109","urban100"]
    
    prepare_benchmarks(benchmark_dir, dataset_list, scale=2)
    print("=== 所有測試集準備完畢 ===")