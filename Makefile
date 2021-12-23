# SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
# SPDX-License-Identifier: MIT

export COCOTB_REDUCED_LOG_FMT=1
export LIBPYTHON_LOC=$(shell cocotb-config --libpython)

all: test_spell

test_execute:
	iverilog -I src -o execute_tb.out test/execute_tb.v src/execute.v
	./execute_tb.out
	gtkwave execute_tb.vcd test/execute_tb.gtkw

test_mem_dff:
	iverilog -I src -o mem_dff_tb.out test/assert.v test/mem_dff_tb.v src/mem_dff.v
	./mem_dff_tb.out
	gtkwave mem_dff_tb.vcd test/mem_dff_tb.gtkw

test_spell:
	iverilog -I src -s spell -s dump -D SPELL_DFF_DELAY -o spell_test.out src/spell.v src/mem.v src/mem_dff.v src/mem_io.v src/execute.v test/dump_spell.v
	MODULE=test.test_spell vvp -M $$(cocotb-config --prefix)/cocotb/libs -m libcocotbvpi_icarus ./spell_test.out

test_spell_show: test_spell
	gtkwave spell_test.vcd test/spell_test.gtkw

test_gate_level:
	iverilog -o spell_gate_level.out -s spell -s dump -g2012 gl/spell.lvs.powered.v test/dump_spell.v -I $(PDK_ROOT)/sky130A
	MODULE=test.test_spell vvp -M $$(cocotb-config --prefix)/cocotb/libs -m libcocotbvpi_icarus spell_gate_level.out
	gtkwave spell_test.vcd test/spell_test.gtkw

format:
	verible-verilog-format --inplace src/*.v test/*.v
