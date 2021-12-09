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

  localparam code_size = 32;
  localparam data_size = 8;

  reg [7:0] code_mem[code_size-1:0];
  reg [7:0] data_mem[data_size-1:0];

  reg [1:0] cycles;

  integer i;

  always @(posedge clock) begin
    if (reset) begin
      cycles <= 0;
      data_ready <= 0;
      for (i = 0; i < code_size; i++) code_mem[i] = 0;
      for (i = 0; i < data_size; i++) data_mem[i] = 0;
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
              `MemoryTypeData: begin
                if (addr < data_size) begin
                  data_mem[addr] <= data_in;
                end
              end
              `MemoryTypeCode: begin
                if (addr < code_size) begin
                  code_mem[addr] <= data_in;
                end
              end
              default: data_ready <= 1'bx;
            endcase
          end else begin
            data_out <= 8'b0;
            case (memory_type)
              `MemoryTypeData: begin
                if (addr < data_size) begin
                  data_out <= data_mem[addr];
                end
              end
              `MemoryTypeCode: begin
                if (addr < code_size) begin
                  data_out <= code_mem[addr];
                end
              end
              default: data_ready <= 1'bx;
            endcase
          end
        end
      end
    end
  end

endmodule
