# PIMSR LUT Tools

This project now includes `pimsr_lut.py`, a first-stage full 8-bit LUT flow for
the active `PIMSR_Net` implementation in `model.py`.

## LUT Contract

- Branches: `left`, `right`, `top`, `bot`
- Address: `addr = (p0 << 16) | (p1 << 8) | p2`
- Depth per branch: `256^3 = 16,777,216`
- Entry per address: 4 signed int8 values
- Entry channel order follows `torch.nn.PixelShuffle(2)`:
  - channel 0: top-left
  - channel 1: top-right
  - channel 2: bottom-left
  - channel 3: bottom-right
- Runtime output:
  1. Read one entry from each of the four branch LUTs.
  2. Sum entries elementwise with at least signed 10-bit accumulation.
  3. Clamp each channel to unsigned `0..255`.
  4. Write the four channels as a 2x2 output block.

## Branch Windows

For LR pixel `(i, j)`, replicate padding is applied before window extraction.

- `left`: `[x[i, j-2], x[i, j-1], x[i, j]]`
- `right`: `[x[i, j], x[i, j+1], x[i, j+2]]`
- `top`: `[x[i-2, j], x[i-1, j], x[i, j]]`
- `bot`: `[x[i, j], x[i+1, j], x[i+2, j]]`

The `left` and `top` branches use the third pixel as the `base / 4` center.
The `right` and `bot` branches use the first pixel as the `base / 4` center.

## Commands

Run the dependency-light checks:

```powershell
python pimsr_lut.py selftest
```

Export all LUTs:

```powershell
python pimsr_lut.py export `
  --checkpoint checkpoints/pimsr_final_swa.pth `
  --output-dir lut_out `
  --batch-size 262144
```

If `checkpoints/pimsr_final_swa.pth` does not exist, the exporter also checks
`checkpoints_2.zip` for the same inner path.

Each branch binary is about 64 MiB. Four branches are about 256 MiB total.
Use `--write-mem` only when a text memory-init file is needed; it is much larger
and slower to generate.

Convert an existing branch binary to Vivado text formats:

```powershell
python pimsr_lut.py convert `
  --input lut_out/left.bin `
  --output lut_out/left.mem `
  --format mem
```

```powershell
python pimsr_lut.py convert `
  --input lut_out/left.bin `
  --output lut_out/left.coe `
  --format coe
```

## Vivado BRAM Formats

The recommended hardware word width is 32 bits:

```text
[31:24] channel 0, top-left
[23:16] channel 1, top-right
[15:8]  channel 2, bottom-left
[7:0]   channel 3, bottom-right
```

Each byte is a signed int8 value in two's-complement form. Sign-extend each byte
before summing the four branch outputs.

Use `.mem` for RTL simulation, inferred ROMs, or XPM memories:

```verilog
reg [31:0] lut [0:16777215];
initial $readmemh("left.mem", lut);
```

For XPM memories, set the init file to the `.mem` path and use 32-bit read data.

Use `.coe` when initializing a Vivado Block Memory Generator IP:

```text
memory_initialization_radix=16;
memory_initialization_vector=
0102feff,
...
00000000;
```

Full 24-bit address LUTs are very large: one 32-bit branch table is 64 MiB as
binary and much larger as text. For real FPGA BRAM capacity, this first-stage
full LUT is mainly a correctness baseline. The next hardware-oriented reduction
step should be equidistant sampling plus tetrahedral interpolation, or external
memory/tiling.

Simulate one input image through LUTs:

```powershell
python pimsr_lut.py simulate `
  --input path/to/lr.png `
  --lut-dir lut_out `
  --output path/to/sr_y.png
```

Generate a hardware trace:

```powershell
python pimsr_lut.py trace `
  --input path/to/lr.png `
  --lut-dir lut_out `
  --output trace.csv
```

Compare a random 8x8 tensor against PyTorch:

```powershell
python pimsr_lut.py compare `
  --checkpoint checkpoints/pimsr_final_swa.pth `
  --lut-dir lut_out
```

This comparison requires PyTorch to be installed in the active Python
environment.

## Trace Columns

`trace.csv` contains one row per LR pixel:

- `row`, `col`
- `addr_left`, `addr_right`, `addr_top`, `addr_bot`
- `out_tl`, `out_tr`, `out_bl`, `out_br`

These columns are intended for RTL testbench validation of address generation,
parallel LUT reads, accumulation, saturation, and 2x2 output placement.

## Compression Experiments

`eval_lut_compression.py` evaluates LUT compression strategies using the full
LUT binaries as the golden source, so it does not need to rerun the PyTorch
model.

Run the default presets for methods 2, 4, 5, and 6:

```powershell
python eval_lut_compression.py --method presets
```

Method 2, sampled LUT plus tetrahedral interpolation:

```powershell
python eval_lut_compression.py --method method2 --input-bits 4
python eval_lut_compression.py --method method2 --input-bits 5
```

Method 4, per-branch input precision in `left,right,top,bot` order:

```powershell
python eval_lut_compression.py --method method4 --branch-bits 4,4,3,3
```

Method 5, per-channel output precision in `TL,TR,BL,BR` order:

```powershell
python eval_lut_compression.py --method method5 --input-bits 4 --channel-bits 8,8,6,6
```

Method 6, uniform output bit-width compression:

```powershell
python eval_lut_compression.py --method method6 --input-bits 4 --output-bits 6
```

Limit the run to selected datasets while iterating:

```powershell
python eval_lut_compression.py --method method2 --input-bits 4 --datasets Set5 Set14
```
