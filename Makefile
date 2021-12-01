# SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
# SPDX-License-Identifier: MIT

all: test_exectue

test_exectue:
	iverilog -g2012 -I src -o execute_tb.out test/execute_tb.v src/execute.v
	./execute_tb.out
	gtkwave execute_tb.vcd test/execute_tb.gtkw
