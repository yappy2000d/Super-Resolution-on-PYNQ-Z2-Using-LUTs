set script_dir [file dirname [file normalize [info script]]]
set rtl_dir [file join $script_dir rtl]
set lut_dir [file join $script_dir lut_sampled_4bit]

add_files -norecurse [list \
    [file join $rtl_dir pimsr_sampled_lut_rom.v] \
    [file join $rtl_dir pimsr_branch_interp_seq.v] \
    [file join $rtl_dir pimsr_lut_pixel_core.v] \
    [file join $rtl_dir pimsr_image_core.v] \
]

add_files -fileset sources_1 -norecurse [list \
    [file join $lut_dir left_4bit.mem] \
    [file join $lut_dir right_4bit.mem] \
    [file join $lut_dir top_4bit.mem] \
    [file join $lut_dir bot_4bit.mem] \
]

set_property file_type {Memory Initialization Files} [get_files *.mem]
update_compile_order -fileset sources_1

puts "PIMSR sampled LUT RTL and memory files added."
puts "Instantiate pimsr_lut_pixel_core and set INIT parameters if Vivado cannot resolve relative .mem paths."
