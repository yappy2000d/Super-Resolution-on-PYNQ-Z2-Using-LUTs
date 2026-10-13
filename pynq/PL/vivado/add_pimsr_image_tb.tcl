set script_dir [file dirname [file normalize [info script]]]
set tb_dir [file join $script_dir tb]
set rtl_dir [file join $script_dir rtl]

add_files -norecurse [list \
    [file join $rtl_dir pimsr_sampled_lut_rom.v] \
    [file join $rtl_dir pimsr_branch_interp_seq.v] \
    [file join $rtl_dir pimsr_lut_pixel_core.v] \
    [file join $rtl_dir pimsr_image_core.v] \
]

add_files -fileset sim_1 -norecurse [list \
    [file join $tb_dir tb_pimsr_image_core.v] \
    [file join $tb_dir image_core_lr_4x4.mem] \
    [file join $tb_dir image_core_hr_8x8.mem] \
]

set_property file_type {Memory Initialization Files} [get_files image_core_lr_4x4.mem]
set_property file_type {Memory Initialization Files} [get_files image_core_hr_8x8.mem]
set_property top tb_pimsr_image_core [get_filesets sim_1]
set_property xsim.simulate.runtime 500us [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "PIMSR image core testbench added to sim_1."
puts "Run Simulation -> Run Behavioral Simulation."
