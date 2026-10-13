set script_dir [file dirname [file normalize [info script]]]
set tb_dir [file join $script_dir tb]

add_files -fileset sim_1 -norecurse [list \
    [file join $tb_dir tb_pimsr_lut_pixel_core_golden.v] \
    [file join $tb_dir pixel_core_vectors.mem] \
]

set_property top tb_pimsr_lut_pixel_core_golden [get_filesets sim_1]
set_property xsim.simulate.runtime 500us [get_filesets sim_1]
update_compile_order -fileset sim_1

puts "PIMSR golden pixel core testbench added to sim_1."
puts "Run Simulation -> Run Behavioral Simulation."
puts "The golden testbench needs more than the default 1000 ns, so runtime is set to 500 us."
