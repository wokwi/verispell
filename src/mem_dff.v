// SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
// SPDX-License-Identifier: MIT

`default_nettype none
//
`timescale 1ns / 1ps

module spell_mem_dff (
    input wire reset,
    input wire clock,
    input wire select,
    input wire [7:0] addr,
    input wire [7:0] data_in,
    input wire [1:0] memory_type,
    input wire write,
    output reg [7:0] data_out,
    output reg data_ready
);

  `include "memtypes.v"

  reg [7:0] code_mem[255:0];
  reg [7:0] data_mem[255:0];
  reg [1:0] cycles;
  
  integer i;

  always @(posedge clock) begin
    if (reset) begin
      cycles <= 0;
      data_ready <= 0;
      for (i = 0; i < 256; i++) code_mem[i] = 0;
      for (i = 0; i < 256; i++) data_mem[i] = 0;
    end else begin
      if (!select) begin
        data_out   <= 8'bx;
        data_ready <= 0;
        cycles     <= 2'b11;
      end else begin
        cycles <= cycles - 1;
        if (cycles == 0 && !data_ready) begin
          data_ready <= 1;
          if (write) begin
            case (memory_type)
              MemoryTypeData: data_mem[addr] <= data_in;
              MemoryTypeCode: code_mem[addr] <= data_in;
              default: data_ready <= 1'bx;
            endcase
          end else begin
            case (memory_type)
              MemoryTypeData: data_out <= data_mem[addr];
              MemoryTypeCode: data_out <= code_mem[addr];
              default: data_ready <= 1'bx;
            endcase
          end
        end
      end
    end
  end

endmodule
