// SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
// SPDX-License-Identifier: MIT

`default_nettype none
//
`timescale 1ns / 1ps

module spell (
    input wire reset,
    input wire clock,

    // Logic anaylzer
    output wire [31:0] la_data_out,

    // Wishbone interface
    input  wire        i_wb_cyc,   // wishbone transaction
    input  wire        i_wb_stb,   // strobe
    input  wire        i_wb_we,    // write enable
    input  wire [31:0] i_wb_addr,  // address
    input  wire [31:0] i_wb_data,  // incoming data
    output wire        o_wb_ack,   // request is completed 
    output reg  [31:0] o_wb_data   // output data
);
  `include "memtypes.v"

  localparam StateFetch = 3'd0;
  localparam StateFetchData = 3'd1;
  localparam StateExecute = 3'd2;
  localparam StateStore = 3'd3;
  localparam StateDelay = 3'd4;
  localparam StateSleep = 3'd5;

  localparam REG_PC = 24'h000;
  localparam REG_SP = 24'h004;
  localparam REG_EXEC = 24'h008;
  localparam REG_RUN = 24'h00c;
  localparam REG_CYCLES_PER_MS = 24'h010;

  localparam REG_STACK_MASK = 24'hffff00;
  localparam REG_STACK_VALUE = 24'h000100;

  reg [2:0] state;
  reg [7:0] pc;
  reg [4:0] sp;
  reg [7:0] opcode;
  reg [7:0] memory_input;
  reg [7:0] stack[31:0];

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
  reg single_step;

  wire [4:0] stack_top_index = sp - 1;
  wire [7:0] stack_top = stack[stack_top_index];

  // Memory related registers
  reg mem_select;
  reg [7:0] mem_addr;
  reg [7:0] mem_write_value;
  reg [1:0] mem_type;
  reg mem_write_en;
  wire [7:0] mem_read_value;
  wire mem_data_ready;

  // Delay related registers
  reg [23:0] cycles_per_ms;
  reg [23:0] delay_counter;

  // Wishbone registers
  reg wb_read_ack;
  reg wb_write_ack;
  assign o_wb_ack = wb_read_ack | wb_write_ack;
  wire wb_read = i_wb_stb && i_wb_cyc && !i_wb_we;
  wire wb_write = i_wb_stb && i_wb_cyc && i_wb_we;
  wire [23:0] wb_addr = i_wb_addr[23:0];

  wire [4:0] wb_stack_addr = wb_addr[4:0];

  // Logic Analyzer Connections:
  // [       Stack Top     | State  |      SP      |         Opcode        |         PC          ]
  // [ 31 30 29 28 27 25 24 23 22 21 20 19 18 17 16 15 14 13 12 11 10 09 08 07 06 05 04 03 02 01 ]

  assign la_data_out = {stack_top, state, sp, opcode, pc};

  // Debug stuff
  reg [63:0] state_name;

  always @(*) begin
    case (state)
      StateFetch: state_name <= 64'("Fetch");
      StateFetchData: state_name <= 64'("FetchDat");
      StateExecute: state_name <= 64'("Execute");
      StateStore: state_name <= 64'("Store");
      StateDelay: state_name <= 64'("Delay");
      StateSleep: state_name <= 64'("Sleep");
      default: state_name <= 64'("Invalid");
    endcase
  end

  spell_execute exec (
      .opcode(opcode),
      .pc(pc),
      .sp(sp),
      .stack_top(stack_top),
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

  spell_mem_dff mem (
      .reset(reset),
      .clock(clock),
      .select(mem_select),
      .addr(mem_addr),
      .data_in(mem_write_value),
      .memory_type(mem_type),
      .write(mem_write_en),
      .data_out(mem_read_value),
      .data_ready(mem_data_ready)
  );

  // Wishbone reads
  always @(posedge clock) begin
    if (reset) begin
      o_wb_data   <= 0;
      wb_read_ack <= 0;
    end else if (wb_read) begin
      case (wb_addr)
        REG_PC: o_wb_data <= {24'b0, pc};
        REG_SP: o_wb_data <= {27'b0, sp};
        REG_EXEC: o_wb_data <= {24'b0, opcode};
        REG_RUN: o_wb_data <= {30'b0, single_step, state != StateSleep};
        REG_CYCLES_PER_MS: o_wb_data <= {8'b0, cycles_per_ms};
        default: begin
          if ((wb_addr & REG_STACK_MASK) == REG_STACK_VALUE) begin
            // TODO: Do unaligned WB read really work?
            o_wb_data <= {24'b0, stack[wb_stack_addr]};
          end else begin
            o_wb_data <= 32'b0;
          end
        end
      endcase
      wb_read_ack <= 1;
    end else begin
      wb_read_ack <= 0;
    end
  end

  // Main logic
  always @(posedge clock) begin
    if (reset) begin
      integer j;
      state <= StateSleep;
      pc    <= 0;
      sp    <= 0;
      for (j = 0; j < 32; j++) stack[j] = 0;
      opcode <= 0;
      mem_select <= 0;
      single_step <= 0;
      wb_write_ack <= 0;
    end else begin
      if (wb_write) begin
        case (wb_addr)
          REG_PC: pc <= i_wb_data[7:0];
          REG_SP: sp <= i_wb_data[4:0];
          REG_EXEC: begin
            opcode <= i_wb_data[7:0];
            state <= StateFetchData;
            single_step <= 1;
          end
          REG_RUN: begin
            if (i_wb_data[0] && state == StateSleep) begin
              state <= StateFetch;
            end
            single_step <= i_wb_data[1];
          end
          REG_CYCLES_PER_MS: cycles_per_ms <= i_wb_data[23:0];
          default:
          // TODO: Do unaligned WB writes really work?
              if ((wb_addr & REG_STACK_MASK) == REG_STACK_VALUE) begin
            stack[wb_stack_addr] = o_wb_data[7:0];
          end
        endcase
        wb_write_ack <= 1;
      end else begin
        wb_write_ack <= 0;
        case (state)
          StateFetch: begin
            // Read next instruction from code memory
            mem_select <= 1;
            mem_type <= MemoryTypeCode;
            mem_addr <= pc;
            mem_write_en <= 0;
            if (mem_data_ready) begin
              mem_select <= 0;
              opcode <= mem_read_value;
              if (opcode == "?" || opcode == "r") state <= StateFetchData;
              else state <= StateExecute;
            end
          end
          StateFetchData: begin
            // Read data for instruction from either code or data memory
            mem_select <= 1;
            mem_type <= (opcode == "?") ? MemoryTypeCode : MemoryTypeData;
            mem_addr <= stack_top;
            mem_write_en <= 0;
            if (mem_data_ready) begin
              mem_select <= 0;
              memory_input <= mem_read_value;
              state <= StateExecute;
            end
          end
          StateExecute: begin
            // Execute a single instruction
            pc <= next_pc;
            sp <= next_sp;
            if (stack_write_count == 1 || stack_write_count == 2) begin
              stack[next_sp-1] = set_stack_top;
            end
            if (stack_write_count == 2) begin
              stack[next_sp-2] = set_stack_belowtop;
            end
            if (memory_write_type == MemoryTypeData || memory_write_type == MemoryTypeCode) begin
              state <= StateStore;
            end else if (sleep || single_step) begin
              state <= StateSleep;
            end else if (delay_amount != 8'b0) begin
              delay_counter <= cycles_per_ms;
              state <= StateDelay;
            end else begin
              state <= StateFetch;
            end
          end
          StateStore: begin
            // Store data from instruction into either code or data memory
            mem_select <= 1;
            mem_type <= memory_write_type;
            mem_addr <= memory_write_data;
            mem_write_value <= memory_write_data;
            mem_write_en <= 1;
            if (mem_data_ready) begin
              mem_select <= 0;
              state <= single_step ? StateSleep : StateFetch;
            end
          end
          StateSleep: begin
            // TODO: raise interrupt to let the CPU know we're sleeping.
            // The only way to leave this state is via CPU intervention.
          end
          StateDelay: begin
            delay_counter <= delay_counter - 1;
            if (delay_counter == 0) begin
              state <= single_step ? StateSleep : StateFetch;
            end
          end
          default: state <= 'x;
        endcase
      end
    end
  end

endmodule