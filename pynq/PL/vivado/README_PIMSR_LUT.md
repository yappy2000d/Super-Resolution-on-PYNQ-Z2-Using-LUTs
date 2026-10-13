# PIMSR 4-bit Sampled LUT for PYNQ-Z2

This folder contains the first BRAM-friendly PIMSR LUT implementation target:

- 4-bit MSB input address per pixel
- 3 pixels per branch address
- 4096 entries per branch
- 32-bit signed int8x4 word per entry
- Four branches: left, right, top, bot
- Sequential 8-vertex tetrahedral interpolation per branch

## Files

- `lut_sampled_4bit/*_4bit.mem`: sampled BRAM initialization files.
- `rtl/pimsr_sampled_lut_rom.v`: synchronous 4096x32 ROM using `$readmemh`.
- `rtl/pimsr_branch_interp_seq.v`: one branch, sequential 8-vertex interpolation.
- `rtl/pimsr_lut_pixel_core.v`: four branches summed and clamped to a 2x2 HR block.
- `add_pimsr_lut.tcl`: add RTL and memory files to the current Vivado project.

## Add To Vivado

Open `vivado/vivado.xpr`, then run this in the Tcl console:

```tcl
source ./add_pimsr_lut.tcl
```

If Vivado cannot resolve the `.mem` file paths during simulation/synthesis,
instantiate the top with absolute INIT parameters, for example:

```verilog
pimsr_lut_pixel_core #(
    .LEFT_INIT("<ABS_PATH_TO_REPO>/pynq/PL/vivado/lut_sampled_4bit/left_4bit.mem"),
    .RIGHT_INIT("<ABS_PATH_TO_REPO>/pynq/PL/vivado/lut_sampled_4bit/right_4bit.mem"),
    .TOP_INIT("<ABS_PATH_TO_REPO>/pynq/PL/vivado/lut_sampled_4bit/top_4bit.mem"),
    .BOT_INIT("<ABS_PATH_TO_REPO>/pynq/PL/vivado/lut_sampled_4bit/bot_4bit.mem")
) core_i (...);
```

## Pixel Core Interface

`pimsr_lut_pixel_core` processes one LR pixel window per transaction.

Input windows must already be replicate-padded and aligned:

- `left_p0,left_p1,left_p2`: `[x[j-2], x[j-1], x[j]]`
- `right_p0,right_p1,right_p2`: `[x[j], x[j+1], x[j+2]]`
- `top_p0,top_p1,top_p2`: `[x[i-2], x[i-1], x[i]]`
- `bot_p0,bot_p1,bot_p2`: `[x[i], x[i+1], x[i+2]]`

Output channel order:

- `out_tl`: top-left HR pixel
- `out_tr`: top-right HR pixel
- `out_bl`: bottom-left HR pixel
- `out_br`: bottom-right HR pixel

## Regenerate LUTs

From `model/LUT/` (requires the full LUT binaries produced by `pimsr_lut.py export`):

```powershell
python export_sampled_lut.py `
  --full-lut-dir lut_out `
  --output-dir ..\..\pynq\PL\vivado\lut_sampled_4bit `
  --input-bits 4 `
  --write-coe
```

Copy the resulting `*_4bit.mem` files into `pynq/PL/ip_repo/pimsr_axi_ip_1_0/src/` as well
before re-packaging the AXI IP.
