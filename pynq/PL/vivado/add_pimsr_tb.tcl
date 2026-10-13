set script_dir [file dirname [file normalize [info script]]]
set tb_dir [file join $script_dir tb]

add_files -fileset sim_1 -norecurse [list \
    [file join $tb_dir tb_pimsr_lut_pixel_core.v] \
]

set_property top tb_pimsr_lut_pixel_core [get_filesets sim_1]
update_compile_order -fileset sim_1

puts "PIMSR pixel core testbench added to sim_1."
puts "Run Simulation -> Run Behavioral Simulation."
