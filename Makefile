# SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
# SPDX-License-Identifier: MIT

all: test_execute

test_execute:
	iverilog -g2012 -I src -o execute_tb.out test/execute_tb.v src/execute.v
	./execute_tb.out
	gtkwave execute_tb.vcd test/execute_tb.gtkw

test_mem_dff:
	iverilog -g2012 -I src -o mem_dff_tb.out test/mem_dff_tb.v src/mem_dff.v
	./mem_dff_tb.out
	gtkwave mem_dff_tb.vcd test/mem_dff_tb.gtkw

format:
	verible-verilog-format --inplace src/*.v test/*.v
