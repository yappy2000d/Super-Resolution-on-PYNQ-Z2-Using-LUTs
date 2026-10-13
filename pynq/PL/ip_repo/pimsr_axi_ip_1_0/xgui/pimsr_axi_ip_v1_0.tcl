# Definitional proc to organize widgets for parameters.
proc init_gui { IPINST } {
  ipgui::add_param $IPINST -name "Component_Name"
  #Adding Page
  set Page_0 [ipgui::add_page $IPINST -name "Page 0"]
  ipgui::add_param $IPINST -name "C_S00_AXI_DATA_WIDTH" -parent ${Page_0} -widget comboBox
  ipgui::add_param $IPINST -name "C_S00_AXI_ADDR_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S00_AXI_BASEADDR" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S00_AXI_HIGHADDR" -parent ${Page_0}
  ipgui::add_param $IPINST -name "IMG_W" -parent ${Page_0}
  ipgui::add_param $IPINST -name "IMG_H" -parent ${Page_0}
  ipgui::add_param $IPINST -name "LR_ADDR_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "HR_ADDR_WIDTH" -parent ${Page_0}


}

proc update_PARAM_VALUE.HR_ADDR_WIDTH { PARAM_VALUE.HR_ADDR_WIDTH } {
	# Procedure called to update HR_ADDR_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.HR_ADDR_WIDTH { PARAM_VALUE.HR_ADDR_WIDTH } {
	# Procedure called to validate HR_ADDR_WIDTH
	return true
}

proc update_PARAM_VALUE.IMG_H { PARAM_VALUE.IMG_H } {
	# Procedure called to update IMG_H when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.IMG_H { PARAM_VALUE.IMG_H } {
	# Procedure called to validate IMG_H
	return true
}

proc update_PARAM_VALUE.IMG_W { PARAM_VALUE.IMG_W } {
	# Procedure called to update IMG_W when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.IMG_W { PARAM_VALUE.IMG_W } {
	# Procedure called to validate IMG_W
	return true
}

proc update_PARAM_VALUE.LR_ADDR_WIDTH { PARAM_VALUE.LR_ADDR_WIDTH } {
	# Procedure called to update LR_ADDR_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.LR_ADDR_WIDTH { PARAM_VALUE.LR_ADDR_WIDTH } {
	# Procedure called to validate LR_ADDR_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_DATA_WIDTH { PARAM_VALUE.C_S00_AXI_DATA_WIDTH } {
	# Procedure called to update C_S00_AXI_DATA_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_DATA_WIDTH { PARAM_VALUE.C_S00_AXI_DATA_WIDTH } {
	# Procedure called to validate C_S00_AXI_DATA_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_ADDR_WIDTH { PARAM_VALUE.C_S00_AXI_ADDR_WIDTH } {
	# Procedure called to update C_S00_AXI_ADDR_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_ADDR_WIDTH { PARAM_VALUE.C_S00_AXI_ADDR_WIDTH } {
	# Procedure called to validate C_S00_AXI_ADDR_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_BASEADDR { PARAM_VALUE.C_S00_AXI_BASEADDR } {
	# Procedure called to update C_S00_AXI_BASEADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_BASEADDR { PARAM_VALUE.C_S00_AXI_BASEADDR } {
	# Procedure called to validate C_S00_AXI_BASEADDR
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_HIGHADDR { PARAM_VALUE.C_S00_AXI_HIGHADDR } {
	# Procedure called to update C_S00_AXI_HIGHADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_HIGHADDR { PARAM_VALUE.C_S00_AXI_HIGHADDR } {
	# Procedure called to validate C_S00_AXI_HIGHADDR
	return true
}


proc update_MODELPARAM_VALUE.C_S00_AXI_DATA_WIDTH { MODELPARAM_VALUE.C_S00_AXI_DATA_WIDTH PARAM_VALUE.C_S00_AXI_DATA_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S00_AXI_DATA_WIDTH}] ${MODELPARAM_VALUE.C_S00_AXI_DATA_WIDTH}
}

proc update_MODELPARAM_VALUE.C_S00_AXI_ADDR_WIDTH { MODELPARAM_VALUE.C_S00_AXI_ADDR_WIDTH PARAM_VALUE.C_S00_AXI_ADDR_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S00_AXI_ADDR_WIDTH}] ${MODELPARAM_VALUE.C_S00_AXI_ADDR_WIDTH}
}

proc update_MODELPARAM_VALUE.IMG_W { MODELPARAM_VALUE.IMG_W PARAM_VALUE.IMG_W } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.IMG_W}] ${MODELPARAM_VALUE.IMG_W}
}

proc update_MODELPARAM_VALUE.IMG_H { MODELPARAM_VALUE.IMG_H PARAM_VALUE.IMG_H } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.IMG_H}] ${MODELPARAM_VALUE.IMG_H}
}

proc update_MODELPARAM_VALUE.LR_ADDR_WIDTH { MODELPARAM_VALUE.LR_ADDR_WIDTH PARAM_VALUE.LR_ADDR_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.LR_ADDR_WIDTH}] ${MODELPARAM_VALUE.LR_ADDR_WIDTH}
}

proc update_MODELPARAM_VALUE.HR_ADDR_WIDTH { MODELPARAM_VALUE.HR_ADDR_WIDTH PARAM_VALUE.HR_ADDR_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.HR_ADDR_WIDTH}] ${MODELPARAM_VALUE.HR_ADDR_WIDTH}
}

