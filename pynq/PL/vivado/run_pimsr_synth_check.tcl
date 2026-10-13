set script_dir [file dirname [file normalize [info script]]]
set report_dir [file join $script_dir reports]
file mkdir $report_dir

set_property top pimsr_lut_pixel_core [get_filesets sources_1]
update_compile_order -fileset sources_1

reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1

if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {
    error "synth_1 did not complete"
}

open_run synth_1 -name synth_1

report_utilization \
    -file [file join $report_dir pimsr_pixel_core_utilization_synth.rpt]

report_utilization \
    -hierarchical \
    -hierarchical_depth 4 \
    -file [file join $report_dir pimsr_pixel_core_utilization_hier_synth.rpt]

report_timing_summary \
    -file [file join $report_dir pimsr_pixel_core_timing_synth.rpt]

puts "PIMSR synthesis check complete."
puts "Reports:"
puts "  [file join $report_dir pimsr_pixel_core_utilization_synth.rpt]"
puts "  [file join $report_dir pimsr_pixel_core_utilization_hier_synth.rpt]"
puts "  [file join $report_dir pimsr_pixel_core_timing_synth.rpt]"
puts "Check BRAM usage in the utilization report. The four sampled LUT ROMs should map mainly to RAMB36/RAMB18."
