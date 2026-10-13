import argparse
import os
import random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.optim as optim
from PIL import Image
from torch.optim.swa_utils import AveragedModel, SWALR
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import functional as TF
from tqdm import tqdm

from model import PIMSR_Net


def rgb_to_y_tensor(img_tensor):
    r, g, b = img_tensor[0], img_tensor[1], img_tensor[2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return y.unsqueeze(0)


class CharbonnierLoss(torch.nn.Module):
    def __init__(self, eps=1e-3):
        super().__init__()
        self.eps = eps

    def forward(self, x, y):
        diff = x - y
        return torch.mean(torch.sqrt(diff * diff + self.eps * self.eps))


class SRDataset(Dataset):
    def __init__(self, hr_dir, lr_dir, hr_patch_size=128, scale_factor=2, is_train=True):
        super().__init__()
        y_names = sorted([f for f in os.listdir(hr_dir) if f.lower().endswith(".png")])
        self.hr_paths = [os.path.join(hr_dir, f) for f in y_names]
        self.lr_paths = [os.path.join(lr_dir, f[:-4] + f"x{scale_factor}.png") for f in y_names]

        missing = [path for path in self.lr_paths if not os.path.exists(path)]
        if missing:
            raise FileNotFoundError(f"Missing LR files, first one: {missing[0]}")

        self.scale = scale_factor
        self.hr_patch_size = hr_patch_size
        self.lr_patch_size = hr_patch_size // scale_factor
        self.is_train = is_train

    def __len__(self):
        return len(self.hr_paths)

    def __getitem__(self, idx):
        hr_img = Image.open(self.hr_paths[idx]).convert("RGB")
        lr_img = Image.open(self.lr_paths[idx]).convert("RGB")

        w_lr, h_lr = lr_img.size
        if self.is_train:
            i_lr = random.randint(0, h_lr - self.lr_patch_size)
            j_lr = random.randint(0, w_lr - self.lr_patch_size)
        else:
            i_lr = (h_lr - self.lr_patch_size) // 2
            j_lr = (w_lr - self.lr_patch_size) // 2

        i_hr = i_lr * self.scale
        j_hr = j_lr * self.scale
        lr_crop = TF.crop(lr_img, i_lr, j_lr, self.lr_patch_size, self.lr_patch_size)
        hr_crop = TF.crop(hr_img, i_hr, j_hr, self.hr_patch_size, self.hr_patch_size)

        if self.is_train:
            if random.random() > 0.5:
                lr_crop = TF.hflip(lr_crop)
                hr_crop = TF.hflip(hr_crop)
            if random.random() > 0.5:
                lr_crop = TF.vflip(lr_crop)
                hr_crop = TF.vflip(hr_crop)

        hr_tensor = TF.to_tensor(hr_crop) * 255.0
        lr_tensor = TF.to_tensor(lr_crop) * 255.0
        return rgb_to_y_tensor(lr_tensor), rgb_to_y_tensor(hr_tensor)


def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)


def seed_worker(worker_id):
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


def set_trainable(module, enabled):
    for param in module.parameters():
        param.requires_grad = enabled


def train(args):
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training Model on {device}", flush=True)
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)

    generator = torch.Generator()
    generator.manual_seed(args.seed)

    train_dataset = SRDataset(
        hr_dir=args.train_hr,
        lr_dir=args.train_lr,
        hr_patch_size=args.hr_patch_size,
        scale_factor=args.scale,
        is_train=True,
    )
    train_dataloader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        worker_init_fn=seed_worker,
        generator=generator,
    )

    val_dataset = SRDataset(
        hr_dir=args.val_hr,
        lr_dir=args.val_lr,
        hr_patch_size=args.hr_patch_size,
        scale_factor=args.scale,
        is_train=False,
    )
    val_dataloader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    model = PIMSR_Net(scale_factor=args.scale).to(device)
    criterion = CharbonnierLoss(eps=1e-3).to(device)
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=args.epochs,
        eta_min=args.eta_min,
    )

    swa_model = AveragedModel(model)
    swa_scheduler = None
    best_val_loss = float("inf")
    history_train_loss = []
    history_val_loss = []

    os.makedirs(args.checkpoint_dir, exist_ok=True)

    print(
        f"Schedule: float warmup epochs 1-{args.qat_start}, "
        f"QAT epochs {args.qat_start + 1}-{args.epochs}, "
        f"SWA starts at epoch {args.swa_start + 1}",
        flush=True,
    )

    for epoch in range(args.epochs):
        epoch_num = epoch + 1
        model.quantize_enabled = epoch >= args.qat_start

        if epoch == 0:
            tqdm.write(f">> [Epoch 1-{args.qat_start}] float warmup")
        if epoch == args.qat_start:
            tqdm.write(f">> [Epoch {epoch_num}-{args.epochs}] early QAT enabled")

        model.train()
        train_loss = 0.0
        pbar = tqdm(train_dataloader, leave=False, desc=f"Epoch {epoch_num:04d}")
        for lr_imgs, hr_imgs in pbar:
            lr_imgs = lr_imgs.to(device)
            hr_imgs = hr_imgs.to(device)

            optimizer.zero_grad(set_to_none=True)
            sr_imgs = model(lr_imgs)
            loss = criterion(sr_imgs, hr_imgs)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            pbar.set_postfix({"Loss": f"{loss.item():.4f}"})

        if epoch == args.swa_start:
            if args.freeze_conv_at_swa:
                set_trainable(model.conv_left, False)
                set_trainable(model.conv_right, False)
                set_trainable(model.conv_top, False)
                set_trainable(model.conv_bot, False)
            optimizer = optim.Adam(
                filter(lambda p: p.requires_grad, model.parameters()),
                lr=args.swa_lr,
            )
            swa_scheduler = SWALR(optimizer, swa_lr=args.swa_lr)
            tqdm.write(f">> [Epoch {epoch_num}] SWA phase started")

        if epoch > args.swa_start and swa_scheduler is not None:
            swa_scheduler.step()
        elif epoch < args.swa_start:
            scheduler.step()

        avg_train_loss = train_loss / len(train_dataloader)
        history_train_loss.append(avg_train_loss)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for lr_imgs, hr_imgs in val_dataloader:
                lr_imgs = lr_imgs.to(device)
                hr_imgs = hr_imgs.to(device)
                sr_imgs = model(lr_imgs)
                loss = criterion(sr_imgs, hr_imgs)
                val_loss += loss.item()

        avg_val_loss = val_loss / len(val_dataloader)
        history_val_loss.append(avg_val_loss)

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save(model.state_dict(), os.path.join(args.checkpoint_dir, "pimsr_best_val.pth"))

        if epoch >= args.swa_start:
            swa_model.update_parameters(model)

        tqdm.write(
            f"Epoch [{epoch_num:04d}/{args.epochs}] | "
            f"Mode: {'QAT' if model.quantize_enabled else 'FLOAT'} | "
            f"Train Loss: {avg_train_loss:.4f} | "
            f"Val Loss: {avg_val_loss:.4f} | "
            f"Best Val: {best_val_loss:.4f} | "
            f"LR: {optimizer.param_groups[0]['lr']:.6f}"
        )

        if epoch_num % args.save_every == 0 or epoch_num == args.epochs:
            ckpt_path = os.path.join(args.checkpoint_dir, f"pimsr_epoch_{epoch_num:04d}.pth")
            torch.save(model.state_dict(), ckpt_path)
            tqdm.write(f"Saved checkpoint: {ckpt_path}")

    if args.swa_start < args.epochs:
        swa_path = os.path.join(args.checkpoint_dir, "pimsr_final_swa.pth")
        model.load_state_dict(swa_model.module.state_dict())
        torch.save(model.state_dict(), swa_path)
        print(f"Saved SWA checkpoint: {swa_path}", flush=True)

    plt.figure(figsize=(10, 6))
    plt.plot(range(1, args.epochs + 1), history_train_loss, label="Train Loss", linewidth=2)
    plt.plot(range(1, args.epochs + 1), history_val_loss, label="Val Loss", linewidth=2)
    plt.title("Early-QAT Training and Validation Loss")
    plt.xlabel("Epochs")
    plt.ylabel("Charbonnier Loss")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.loss_curve, dpi=300)
    print(f"Saved loss curve: {args.loss_curve}", flush=True)


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Train PIMSR with early QAT.")
    parser.add_argument("--epochs", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--hr-patch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--eta-min", type=float, default=1e-6)
    parser.add_argument("--qat-start", type=int, default=500)
    parser.add_argument("--swa-start", type=int, default=3500)
    parser.add_argument("--swa-lr", type=float, default=5e-5)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--train-hr", default="./datasets/train/Y")
    parser.add_argument("--train-lr", default="./datasets/train/X")
    parser.add_argument("--val-hr", default="./datasets/validate/Y")
    parser.add_argument("--val-lr", default="./datasets/validate/X")
    parser.add_argument("--checkpoint-dir", default="checkpoints")
    parser.add_argument("--loss-curve", default="loss_curve.png")
    parser.add_argument("--freeze-conv-at-swa", action="store_true")
    return parser


if __name__ == "__main__":
    train(build_arg_parser().parse_args())
