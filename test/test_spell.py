# SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from cocotbext.wishbone.driver import WishboneMaster, WBOp
from test.edge_monitor import RisingEdgeCounter
from test.wb_ram import WishboneRAM


def bit(n):
    return 1 << n


# Wishbone bus registers
reg_pc = 0x3000_0000
reg_sp = 0x3000_0004
reg_exec = 0x3000_0008
reg_ctrl = 0x3000_000C
reg_cycles_per_ms = 0x3000_0010
reg_stack_top = 0x3000_0014
reg_stack_push = 0x3000_0018
reg_int_enable = 0x3000_0020
reg_int = 0x3000_0024

CTRL_RUN = bit(0)
CTRL_STEP = bit(1)
CTRL_SRAM_ENABLE = bit(2)
CTRL_EDGE_INTERRUPTS = bit(3)

INTR_SLEEP = bit(0)
INTR_STOP = bit(1)

stateNames = [
    "Fetch",
    "FetchDat",
    "Execute",
    "Store",
    "Delay",
    "Sleep",
    "Invalid",
    "Invalid",
]

wishbone_signals = {
    "cyc": "i_wb_cyc",
    "stb": "i_wb_stb",
    "we": "i_wb_we",
    "adr": "i_wb_addr",
    "datwr": "i_wb_data",
    "datrd": "o_wb_data",
    "ack": "o_wb_ack",
}

ram_bus_signals = {
    "cyc": "rambus_wb_cyc_o",
    "stb": "rambus_wb_stb_o",
    "we": "rambus_wb_we_o",
    "adr": "rambus_wb_addr_o",
    "sel": "rambus_wb_sel_o",
    "datwr": "rambus_wb_dat_o",
    "datrd": "rambus_wb_dat_i",
    "ack": "rambus_wb_ack_i",
}


async def reset(dut):
    dut.reset.value = 1
    await ClockCycles(dut.clock, 5)
    dut.reset.value = 0
    await ClockCycles(dut.clock, 5)


async def make_clock(dut, clock_mhz):
    clk_period_ns = round(1 / clock_mhz * 1000, 2)
    dut._log.info("input clock = %d MHz, period = %.2f ns" % (clock_mhz, clk_period_ns))
    clock = Clock(dut.clock, clk_period_ns, units="ns")
    clock_sig = cocotb.fork(clock.start())
    return clock_sig


class SpellController:
    def __init__(self, dut, wishbone):
        self._dut = dut
        self._wishbone = wishbone
        self._ctrl_flags = 0
        self._wbram = WishboneRAM(dut, dut.rambus_wb_clk_o, ram_bus_signals)
        self.sram = self._wbram.data

    async def wb_read(self, addr):
        res = await self._wishbone.send_cycle([WBOp(addr)])
        return res[0].datrd

    async def wb_write(self, addr, value):
        await self._wishbone.send_cycle([WBOp(addr, value)])

    def enable_rambus(self):
        self._ctrl_flags |= CTRL_SRAM_ENABLE

    def enable_edge_interrupts(self):
        self._ctrl_flags |= CTRL_EDGE_INTERRUPTS

    def logic_read(self):
        value = self._dut.la_data_out.value
        state = stateNames[(value >> 21) & 0x7]
        return {
            "pc": value & 0xFF,
            "opcode": (value >> 8) & 0xFF,
            "sp": (value >> 16) & 0x1F,
            "state": state,
            "stopped": state == "Sleep",
            "top": (value >> 24) & 0xFF,
        }

    async def ensure_cpu_stopped(self):
        logic = self.logic_read()
        while not logic["stopped"]:
            await self.wb_write(reg_ctrl, self._ctrl_flags | CTRL_STEP)
            logic = self.logic_read()

    async def single_step(self):
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_ctrl, self._ctrl_flags | CTRL_STEP | CTRL_RUN)
        await self.ensure_cpu_stopped()

    async def execute(self, wait=True):
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_ctrl, self._ctrl_flags | CTRL_RUN)
        while wait and (await self.wb_read(reg_ctrl) & CTRL_RUN):
            pass

    async def exec_step(self, opcode):
        if type(opcode) == str:
            opcode = ord(opcode)
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_exec, opcode)
        await self.ensure_cpu_stopped()

    async def push(self, value):
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_stack_push, value)

    async def set_pc(self, value):
        await self.wb_write(reg_pc, value)

    async def set_sp(self, value):
        await self.wb_write(reg_sp, value)

    async def set_sp_read_stack(self, index):
        await self.set_sp(index)
        return await self.wb_read(reg_stack_top)

    async def write_progmem(self, addr, value):
        """
        Writes a value to progmem by executing an instruction on the CPU.
        """
        if type(value) == str:
            value = ord(value)
        await self.push(value)
        await self.push(addr)
        await self.exec_step("!")

    async def write_program(self, opcodes, offset=0):
        for index, opcode in enumerate(opcodes):
            await self.write_progmem(offset + index, opcode)


async def create_spell(dut):
    if hasattr(dut, "VPWR"):
        # Running a gate-level simulation, connect the power and ground signals
        dut.VGND <= 0
        dut.VPWR <= 1

    wishbone = WishboneMaster(
        dut, "", dut.clock, width=32, timeout=10, signals_dict=wishbone_signals
    )
    spell = SpellController(dut, wishbone)
    return spell


@cocotb.test()
async def test_add(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    # Write a program that adds two numbers, then goes to sleep
    await spell.write_progmem(0, 42)
    await spell.write_progmem(1, 58)
    await spell.write_progmem(2, "+")
    await spell.write_progmem(3, "z")

    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 4
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 100  # The sum

    clock_sig.kill()


@cocotb.test()
async def test_sub(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([66, 55, "-", "z"])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 4
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 11  # The difference

    clock_sig.kill()


@cocotb.test()
async def test_bitwise(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program(
        [0x88, 0xF0, "&", 0x88, 0xF0, "|", 0x88, 0xF0, "^", 0x88, ">", 0x88, "<", "z"]
    )
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 14
    assert logic_data["sp"] == 5
    assert (await spell.set_sp_read_stack(5)) == 0x10  # 0x88 << 1
    assert (await spell.set_sp_read_stack(4)) == 0x44  # 0x88 >> 1
    assert (await spell.set_sp_read_stack(3)) == 0x78  # 0x88 ^ 0xf0
    assert (await spell.set_sp_read_stack(2)) == 0xF8  # 0x88 | 0xf0
    assert (await spell.set_sp_read_stack(1)) == 0x80  # 0x88 & 0xf0

    clock_sig.kill()


@cocotb.test()
async def test_dup(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([12, "2", "z"])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 3
    assert logic_data["sp"] == 2
    assert logic_data["top"] == 12

    await spell.set_sp(1)
    logic_data = spell.logic_read()
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 12

    clock_sig.kill()


@cocotb.test()
async def test_exchange(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([89, 96, "x", "z"])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 4
    assert logic_data["sp"] == 2
    assert logic_data["top"] == 89

    await spell.set_sp(1)
    logic_data = spell.logic_read()
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 96

    clock_sig.kill()


@cocotb.test()
async def test_jmp(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([22, "="])
    await spell.single_step()
    await spell.single_step()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 22
    assert logic_data["sp"] == 0

    clock_sig.kill()


@cocotb.test()
async def test_loop(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([2, 1, "@"])
    await spell.single_step()
    await spell.single_step()
    await spell.single_step()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 1
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 1

    await spell.single_step()
    await spell.single_step()
    logic_data = spell.logic_read()
    assert logic_data["pc"] == 1
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 0

    await spell.single_step()
    await spell.single_step()
    logic_data = spell.logic_read()
    assert logic_data["pc"] == 3
    assert logic_data["sp"] == 0

    clock_sig.kill()


@cocotb.test()
async def test_exchange(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([89, 96, "x", "z"])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 4
    assert logic_data["sp"] == 2
    assert logic_data["top"] == 89

    await spell.set_sp(1)
    logic_data = spell.logic_read()
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 96

    clock_sig.kill()


@cocotb.test()
async def test_delay(dut):
    delay_ms_cycles = 32
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.wb_write(reg_cycles_per_ms, delay_ms_cycles)
    await spell.write_program([10, ",", "z"])
    await spell.execute(False)

    await ClockCycles(dut.clock, 9 * delay_ms_cycles)
    logic_data = spell.logic_read()
    assert logic_data["pc"] == 2
    assert logic_data["state"] == "Delay"

    await ClockCycles(dut.clock, 2 * delay_ms_cycles)
    logic_data = spell.logic_read()
    assert logic_data["pc"] == 3
    assert logic_data["sp"] == 0

    clock_sig.kill()


@cocotb.test()
async def test_stop(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_progmem(0, 0xFF)
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 1
    assert logic_data["sp"] == 0

    clock_sig.kill()


@cocotb.test()
async def test_code_mem_read(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([4, "?", "z", 0, 45])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 3
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 45

    clock_sig.kill()


@cocotb.test()
async def test_code_mem_write(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([5, 3, "!", "z", "z"])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 5
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 5

    clock_sig.kill()


@cocotb.test()
async def test_data_mem(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([10, 4, "w", 15, 4, "r", "z"])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 7
    assert logic_data["sp"] == 2
    assert logic_data["top"] == 10

    clock_sig.kill()


@cocotb.test()
async def test_data_mem_regs(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    # Write RAM through Wishbone registers
    await spell.push(255)
    await spell.push(2)
    await spell.exec_step("w")

    sp = await spell.wb_read(reg_sp)
    assert sp == 0

    await spell.write_program([2, "r", 11, 3, "w", "z"])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["pc"] == 6
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 255

    # Now read RAM through Wishbone registers and compare
    await spell.push(3)
    await spell.exec_step("r")

    logic_data = spell.logic_read()
    assert logic_data["sp"] == 2
    assert logic_data["top"] == 11

    clock_sig.kill()


@cocotb.test()
async def test_io(dut):
    PIN = 0x36
    DDR = 0x37
    PORT = 0x38

    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.push(0xF0)
    await spell.push(DDR)
    await spell.exec_step("w")
    assert dut.io_oeb.value == 0x0F

    await spell.push(0x30)
    await spell.push(PORT)
    await spell.exec_step("w")
    assert dut.io_out.value == 0x30

    await spell.push(0x50)
    await spell.push(PIN)
    await spell.exec_step("w")
    assert dut.io_out.value == 0x60

    dut.io_in = 0x7A
    await spell.push(PIN)
    await spell.exec_step("r")
    logic_data = spell.logic_read()
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 0x7A

    clock_sig.kill()


@cocotb.test()
async def test_io_pin_bug(dut):
    PIN = 0x36

    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([0xF0, PIN, "w", 0x55, PIN, "w", "z"])
    await spell.execute()
    assert dut.io_out.value == 0xA5  # 0xf0 ^ 0x55

    clock_sig.kill()


@cocotb.test()
async def test_rambus(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    spell.enable_rambus()

    # Write a small test program directly to RAM
    spell.sram[0] = 0x55
    spell.sram[1] = 166
    spell.sram[2] = ord("w")
    spell.sram[3] = 0x42
    spell.sram[4] = 142
    spell.sram[5] = ord("!")
    spell.sram[6] = 100
    spell.sram[7] = ord("r")
    spell.sram[8] = ord("z")

    # Write some data at data memory location 100 (address 256 + 100)
    spell.sram[256 + 100] = 78

    # Run the test program
    await spell.execute()

    # Check that sram writes went successfully
    assert spell.sram[256 + 166] == 0x55
    assert spell.sram[142] == 0x42

    # Check that sram read went successfully
    logic_data = spell.logic_read()
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 78

    clock_sig.kill()


@cocotb.test()
async def test_interrupts(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program(["z"])
    await spell.execute()
    assert await spell.wb_read(reg_int) == INTR_SLEEP

    assert dut.interrupt.value == 0
    await spell.wb_write(reg_int_enable, INTR_SLEEP | INTR_STOP)
    assert dut.interrupt.value == 1

    # Clear the sleep interrupt, check that the interrupt line goes down
    await spell.wb_write(reg_int, INTR_SLEEP)
    assert dut.interrupt.value == 0
    assert await spell.wb_read(reg_int) == 0

    # Now check the stop interrupt
    await spell.set_pc(0)
    await spell.write_program([0xFF])
    await spell.execute()
    assert dut.interrupt.value == 1
    assert await spell.wb_read(reg_int) == INTR_STOP

    await spell.wb_write(reg_int_enable, 0)
    assert dut.interrupt.value == 0
    await spell.wb_write(reg_int_enable, INTR_SLEEP | INTR_STOP)
    assert dut.interrupt.value == 1

    # Clear the STOP interrupt, check that the interrupt line goes down
    await spell.wb_write(reg_int, INTR_STOP)
    assert dut.interrupt.value == 0
    assert await spell.wb_read(reg_int) == 0

    clock_sig.kill()


@cocotb.test()
async def test_edge_interrupts(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    spell.enable_edge_interrupts()
    await spell.write_program(["z"])
    await spell.execute()
    assert await spell.wb_read(reg_int) == INTR_SLEEP

    edge_counter = RisingEdgeCounter("irq", dut.interrupt)

    assert dut.interrupt.value == 0
    await spell.wb_write(reg_int_enable, INTR_SLEEP | INTR_STOP)
    assert edge_counter.counter == 1
    assert await spell.wb_read(reg_int) == 1

    # Disable and enable the interrupt - should pulse the interrupt line again
    await spell.wb_write(reg_int_enable, 0)
    await spell.wb_write(reg_int_enable, INTR_SLEEP | INTR_STOP)
    assert edge_counter.counter == 2

    edge_counter.reset()
    # Clear the sleep interrupt, check that the register updates correctly and interrupt is not fired again
    await spell.wb_write(reg_int, INTR_SLEEP)
    assert await spell.wb_read(reg_int) == 0
    assert edge_counter.counter == 0

    clock_sig.kill()


@cocotb.test()
async def test_intg_multiply(dut):
    """
    SPELL integration test: multiplies two numbers
    """
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    # fmt: off
    await spell.write_program([
        10, 11,
        1, 'w',
        0, 'x',
        'x', 1, 'r', '+',
        'x', 6, '@',
        1, 'r', '-',
        'z',    
    ])
    # fmt: on

    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data["sp"] == 1
    assert logic_data["top"] == 110

    clock_sig.kill()
