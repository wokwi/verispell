// SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
// SPDX-License-Identifier: MIT

`timescale 1ns / 1ps
//
`default_nettype none

module test_spell_mem_dff ();
  `include "memtypes.v"

  reg reset;
  reg clock;
  reg select;
  reg [7:0] addr;
  reg [7:0] data_in;
  reg [1:0] memory_type;
  reg write;
  wire [7:0] data_out;
  wire data_ready;

  spell_mem_dff mem (
      .reset(reset),
      .clock(clock),
      .select(select),
      .addr(addr),
      .data_in(data_in),
      .memory_type(memory_type),
      .write(write),
      .data_out(data_out),
      .data_ready(data_ready)
  );

  initial begin
    clock = 0;
    forever begin
      #5 clock = ~clock;
    end
  end

  initial begin
    reset  = 1;
    select = 0;
    #20 reset = 0;
    #10 reset = 0;

    // Write a byte to data location 50
    addr = 50;
    data_in = 42;
    write = 1;
    memory_type = MemoryTypeData;
    select = 1;
    #90 select = 0;
    data_in = 0;
    #10 reset = 0;

    // Read a byte from code location 50
    addr = 50;
    write = 0;
    memory_type = MemoryTypeCode;
    select = 1;
    #90 select = 0;
    #10 reset = 0;

    // Read a byte from data location 50
    addr = 50;
    write = 0;
    memory_type = MemoryTypeData;
    select = 1;
    #90 select = 0;
    #10 reset = 0;

    // Read a byte from data location 60
    addr = 60;
    write = 0;
    memory_type = MemoryTypeData;
    select = 1;
    #90 select = 0;
    #10 reset = 0;

    // Write a byte to code location 50 
    addr = 50;
    data_in = 99;
    write = 1;
    memory_type = MemoryTypeCode;
    select = 1;
    #90 select = 0;
    data_in = 0;
    #10 reset = 0;

    // Read a byte from code location 50
    addr = 50;
    write = 0;
    memory_type = MemoryTypeCode;
    select = 1;
    #90 select = 0;
    #10 reset = 0;

    // Read a byte from data location 50
    addr = 50;
    write = 0;
    memory_type = MemoryTypeData;
    select = 1;
    #90 select = 0;
    #10 reset = 0;

    $finish();
  end

  initial begin
    $dumpfile("mem_dff_tb.vcd");
    $dumpvars(0, test_spell_mem_dff);
  end
endmodule
