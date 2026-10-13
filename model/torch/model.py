# 硬體友善版本

import torch
import torch.nn as nn
import torch.nn.functional as F

class FakeQuantizeQmn_STE(torch.autograd.Function):
    """
    自定義的 QAT 直通估計器
    """
    @staticmethod
    def forward(ctx, x, total_bits, frac_bits, is_signed=True):
        # 1. 計算縮放因子 (2^n)
        scale = 2 ** frac_bits
        
        # 2. 計算硬體數值上下界
        if is_signed:
            # 例如 8-bit signed: qmin = -128, qmax = 127
            qmin = -(2 ** (total_bits - 1))
            qmax = (2 ** (total_bits - 1)) - 1
        else:
            qmin = 0
            qmax = (2 ** total_bits) - 1
            
        # 3. 乘上 scale，四捨五入到整數，然後限制範圍 (Clip)
        x_scaled = torch.round(x * scale)
        x_clamped = torch.clamp(x_scaled, qmin, qmax)
        
        # 4. 除回 scale，轉回浮點數供後續運算 (模擬硬體的定點數刻度)
        x_quant = x_clamped / scale
        
        return x_quant

    @staticmethod
    def backward(ctx, grad_output):
        # STE 的魔法：反向傳播時，把梯度原封不動傳回去，假裝沒有 round() 的發生
        return grad_output, None, None, None

class QmnQuantizer(nn.Module):
    def __init__(self, total_bits=8, frac_bits=0, is_signed=True):
        super(QmnQuantizer, self).__init__()
        self.total_bits = total_bits
        self.frac_bits = frac_bits
        self.is_signed = is_signed

    def forward(self, x):
        return FakeQuantizeQmn_STE.apply(x, self.total_bits, self.frac_bits, self.is_signed)

# 使用 Nearest Neighbor 只需要在轉換成 LUT 後加上 1/4 的中央像素
def make_1x1_block(in_channels, out_channels, num_layers=8):
    """建立獨立的 1x1 卷積區塊，確保每一層都有 ReLU"""
    layers = []
    for i in range(num_layers - 1):
        layers.append(nn.Conv2d(in_channels if i == 0 else 128, 128, kernel_size=1))
        layers.append(nn.ReLU(inplace=True))
    # 最後輸出高頻殘差，不加非線性
    layers.append(nn.Conv2d(128, out_channels, kernel_size=1))
    return nn.Sequential(*layers)

class PIMSR_Net(nn.Module):
    def __init__(self, scale_factor=2, lut_bits=8, lut_frac_bits=0, is_signed=True):
        super(PIMSR_Net, self).__init__()
        self.scale_factor = scale_factor
        r2 = scale_factor ** 2
        
        # 空間特徵提取 (4個方向獨立)
        self.conv_left  = nn.Conv2d(1, 64, kernel_size=(1, 3), padding=0)
        self.conv_right = nn.Conv2d(1, 64, kernel_size=(1, 3), padding=0)
        self.conv_top   = nn.Conv2d(1, 64, kernel_size=(3, 1), padding=0)
        self.conv_bot   = nn.Conv2d(1, 64, kernel_size=(3, 1), padding=0)
        
        # 獨立的非線性轉換 (為未來拆成 4 個 LUT 做準備)
        self.mlp_left  = make_1x1_block(64, r2)
        self.mlp_right = make_1x1_block(64, r2)
        self.mlp_top   = make_1x1_block(64, r2)
        self.mlp_bot   = make_1x1_block(64, r2)

        self.quantize_enabled = False
        self.lut_quantizer = QmnQuantizer(total_bits=lut_bits, frac_bits=lut_frac_bits, is_signed=is_signed)
        
        self.pixel_shuffle = nn.PixelShuffle(scale_factor)

    def forward(self, x):
        # base = F.interpolate(x, scale_factor=self.scale_factor, mode='nearest')
        base = x.repeat(1, self.scale_factor**2, 1, 1)
        
        x_pad = F.pad(x, (2, 2, 2, 2), mode='replicate')
        
        feat_left  = self.conv_left(x_pad[:, :, 2:-2, 0:-2])
        feat_right = self.conv_right(x_pad[:, :, 2:-2, 2:])
        feat_top   = self.conv_top(x_pad[:, :, 0:-2, 2:-2])
        feat_bot   = self.conv_bot(x_pad[:, :, 2:, 2:-2])
        
        res_left  = self.mlp_left(feat_left)
        res_right = self.mlp_right(feat_right)
        res_top   = self.mlp_top(feat_top)
        res_bot   = self.mlp_bot(feat_bot)
        
        if self.quantize_enabled:
            lut_val_left  = res_left  + (base / 4.0)
            lut_val_right = res_right + (base / 4.0)
            lut_val_top   = res_top   + (base / 4.0)
            lut_val_bot   = res_bot   + (base / 4.0)
            
            lut_q_left  = self.lut_quantizer(lut_val_left)
            lut_q_right = self.lut_quantizer(lut_val_right)
            lut_q_top   = self.lut_quantizer(lut_val_top)
            lut_q_bot   = self.lut_quantizer(lut_val_bot)

            sum_q = lut_q_left + lut_q_right + lut_q_top + lut_q_bot
            out_feat = torch.clamp(sum_q, 0.0, 255.0)
        else:
            res_sum = res_left + res_right + res_top + res_bot
            out_feat = res_sum + base
        
        sr_y = self.pixel_shuffle(out_feat)
        
        return sr_y

# 測試模型架構
if __name__ == "__main__":
    # 宣告模型 (放大因子為 2，對應論文常見的 4K 超解析度場景)
    model = PIMSR_Net(scale_factor=2)
    
    dummy_input = torch.randn(1, 1, 720, 1280) 
    
    output = model(dummy_input)
    
    print("模型結構：\n", model)
    print("輸入 Tensor 尺寸:", dummy_input.shape)
    print("輸出 Tensor 尺寸:", output.shape)
