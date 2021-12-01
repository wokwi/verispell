// SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
// SPDX-License-Identifier: MIT

`timescale 1ns / 1ps
//
`default_nettype none

module test_spell_execute ();
  reg [7:0] stack[31:0];
  reg [7:0] opcode;
  reg [7:0] pc;
  reg [4:0] sp;
  reg [7:0] memory_input;
  wire [7:0] next_pc;
  wire [4:0] next_sp;
  wire [1:0] stack_write_count;
  wire [7:0] set_stack_top;
  wire [7:0] set_stack_belowtop;
  wire [1:0] memory_write_type;
  wire [7:0] memory_write_addr;
  wire [7:0] memory_write_data;
  wire [7:0] delay_amount;
  wire sleep;

  // for VCD dump:
  wire [7:0] stack0 = stack[0];
  wire [7:0] stack1 = stack[1];

  spell_execute exec (
      .opcode(opcode),
      .pc(pc),
      .sp(sp),
      .stack_top(stack[sp-1]),
      .stack_belowtop(stack[sp-2]),
      .memory_input(memory_input),
      .next_pc(next_pc),
      .next_sp(next_sp),
      .stack_write_count(stack_write_count),
      .set_stack_top(set_stack_top),
      .set_stack_belowtop(set_stack_belowtop),
      .memory_write_type(memory_write_type),
      .memory_write_addr(memory_write_addr),
      .memory_write_data(memory_write_data),
      .delay_amount(delay_amount),
      .sleep(sleep)
  );

  initial begin
    opcode = "A";
    pc = 0;
    sp = 2;
    memory_input = 8'h42;
    stack[0] = 15;
    stack[1] = 10;

    // Arithemetic
    #10 opcode = "+";
    #10 opcode = "-";
    #10 opcode = "&";
    #10 opcode = "|";
    #10 opcode = "^";
    #10 opcode = ">";
    #10 opcode = "<";
    // Stack
    #10 opcode = "x";
    #10 opcode = "2";
    // Flow control
    #10 opcode = "=";
    #10 opcode = "@";
    #10 stack[0] = 0;
    opcode = "@";
    #10 stack[0] = 15;
    // I/O
    #10 opcode = "?";
    #10 opcode = "r";
    #10 opcode = "!";
    #10 opcode = "w";
    // Misc
    #10 opcode = ",";
    #10 opcode = "z";
    #10;
  end

  initial begin
    $dumpfile("execute_tb.vcd");
    $dumpvars(0, test_spell_execute);
  end
endmodule
