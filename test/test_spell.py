import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from cocotbext.wishbone.driver import WishboneMaster, WBOp

# Wishbone bus registers
reg_pc = 0x3000_0000
reg_sp = 0x3000_0004
reg_exec = 0x3000_0008
reg_run = 0x3000_000c
reg_cycles_per_ms = 0x3000_0010
reg_stack_top = 0x3000_0014
reg_stack_push = 0x3000_0018

stateNames = ["Fetch", "FetchDat", "Execute",
              "Store", "Delay", "Sleep", "Invalid", "Invalid"]

wishbone_signals = {
    "cyc":  "i_wb_cyc",
    "stb":  "i_wb_stb",
    "we":   "i_wb_we",
    "adr":  "i_wb_addr",
    "datwr": "i_wb_data",
    "datrd": "o_wb_data",
    "ack":  "o_wb_ack"
}


async def reset(dut):
    dut.reset.value = 1
    await ClockCycles(dut.clock, 5)
    dut.reset.value = 0
    await ClockCycles(dut.clock, 5)


async def make_clock(dut, clock_mhz):
    clk_period_ns = round(1 / clock_mhz * 1000, 2)
    dut._log.info("input clock = %d MHz, period = %.2f ns" %
                  (clock_mhz, clk_period_ns))
    clock = Clock(dut.clock, clk_period_ns, units="ns")
    clock_sig = cocotb.fork(clock.start())
    return clock_sig


class SpellController:
    def __init__(self, dut, wishbone):
        self._dut = dut
        self._wishbone = wishbone

    async def wb_read(self, addr):
        res = await self._wishbone.send_cycle([WBOp(addr)])
        return res[0].datrd

    async def wb_write(self, addr, value):
        await self._wishbone.send_cycle([WBOp(addr, value)])

    def logic_read(self):
        value = self._dut.la_data_out.value
        state = stateNames[(value >> 21) & 0x7]
        return {
            'pc': value & 0xff,
            'opcode': (value >> 8) & 0xff,
            'sp': (value >> 16) & 0x1f,
            'state': state,
            'stopped': state == "Sleep",
            'top': (value >> 24) & 0xff,
        }

    async def ensure_cpu_stopped(self):
        logic = self.logic_read()
        while not logic['stopped']:
            await self.wb_write(reg_run, 0b10)
            logic = self.logic_read()

    async def single_step(self):
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_run, 0b11)
        await self.ensure_cpu_stopped()

    async def execute(self, wait=True):
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_run, 0b01)
        while wait and (await self.wb_read(reg_run) & 1):
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
        await self.exec_step('!')

    async def write_program(self, opcodes, offset=0):
        for index, opcode in enumerate(opcodes):
            await self.write_progmem(offset + index, opcode)


async def create_spell(dut):
    if hasattr(dut, 'VPWR'):
        # Running a gate-level simulation, connect the power and ground signals
        dut.VGND <= 0
        dut.VPWR <= 1

    wishbone = WishboneMaster(
        dut, "", dut.clock, width=32, timeout=10, signals_dict=wishbone_signals)
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
    await spell.write_progmem(2, '+')
    await spell.write_progmem(3, 'z')

    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 4
    assert logic_data['sp'] == 1
    assert logic_data['top'] == 100  # The sum

    clock_sig.kill()


@cocotb.test()
async def test_sub(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([66, 55, '-', 'z'])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 4
    assert logic_data['sp'] == 1
    assert logic_data['top'] == 11  # The difference

    clock_sig.kill()


@cocotb.test()
async def test_bitwise(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([
        0x88, 0xf0, '&',
        0x88, 0xf0, '|',
        0x88, 0xf0, '^',
        0x88, '>',
        0x88, '<',
        'z'])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 14
    assert logic_data['sp'] == 5
    assert (await spell.set_sp_read_stack(5)) == 0x10  # 0x88 << 1
    assert (await spell.set_sp_read_stack(4)) == 0x44  # 0x88 >> 1
    assert (await spell.set_sp_read_stack(3)) == 0x78  # 0x88 ^ 0xf0
    assert (await spell.set_sp_read_stack(2)) == 0xf8  # 0x88 | 0xf0
    assert (await spell.set_sp_read_stack(1)) == 0x80  # 0x88 & 0xf0

    clock_sig.kill()


@cocotb.test()
async def test_dup(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([12, '2', 'z'])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 3
    assert logic_data['sp'] == 2
    assert logic_data['top'] == 12

    await spell.set_sp(1)
    logic_data = spell.logic_read()
    assert logic_data['sp'] == 1
    assert logic_data['top'] == 12

    clock_sig.kill()


@cocotb.test()
async def test_exchange(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([89, 96, 'x', 'z'])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 4
    assert logic_data['sp'] == 2
    assert logic_data['top'] == 89

    await spell.set_sp(1)
    logic_data = spell.logic_read()
    assert logic_data['sp'] == 1
    assert logic_data['top'] == 96

    clock_sig.kill()


@cocotb.test()
async def test_jmp(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([22, '='])
    await spell.single_step()
    await spell.single_step()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 22
    assert logic_data['sp'] == 0

    clock_sig.kill()


@cocotb.test()
async def test_loop(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([2, 1, '@'])
    await spell.single_step()
    await spell.single_step()
    await spell.single_step()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 1
    assert logic_data['sp'] == 1
    assert logic_data['top'] == 1

    await spell.single_step()
    await spell.single_step()
    logic_data = spell.logic_read()
    assert logic_data['pc'] == 1
    assert logic_data['sp'] == 1
    assert logic_data['top'] == 0

    await spell.single_step()
    await spell.single_step()
    logic_data = spell.logic_read()
    assert logic_data['pc'] == 3
    assert logic_data['sp'] == 0

    clock_sig.kill()


@cocotb.test()
async def test_exchange(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_program([89, 96, 'x', 'z'])
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 4
    assert logic_data['sp'] == 2
    assert logic_data['top'] == 89

    await spell.set_sp(1)
    logic_data = spell.logic_read()
    assert logic_data['sp'] == 1
    assert logic_data['top'] == 96

    clock_sig.kill()


@cocotb.test()
async def test_delay(dut):
    delay_ms_cycles = 32
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.wb_write(reg_cycles_per_ms, delay_ms_cycles)
    await spell.write_program([10, ',', 'z'])
    await spell.execute(False)

    await ClockCycles(dut.clock, 9 * delay_ms_cycles)
    logic_data = spell.logic_read()
    assert logic_data['pc'] == 2
    assert logic_data['state'] == 'Delay'

    await ClockCycles(dut.clock, 2 * delay_ms_cycles)
    logic_data = spell.logic_read()
    assert logic_data['pc'] == 3
    assert logic_data['sp'] == 0

    clock_sig.kill()


@cocotb.test()
async def test_stop(dut):
    spell = await create_spell(dut)
    clock_sig = await make_clock(dut, 10)
    await reset(dut)

    await spell.write_progmem(0, 0xff)
    await spell.execute()

    logic_data = spell.logic_read()
    assert logic_data['pc'] == 1
    assert logic_data['sp'] == 0

    clock_sig.kill()
