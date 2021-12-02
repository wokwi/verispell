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
reg_stack_start = 0x3000_0100

stateNames = ["Fetch", "FetchDat", "Execute",
              "Store", "Delay", "Sleep", "Invalid", "Invalid"]


async def reset(dut):
    dut.reset.value = 1
    await ClockCycles(dut.clock, 5)
    dut.reset.value = 0
    await ClockCycles(dut.clock, 5)


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

    async def execute(self):
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_run, 0b01)
        while await self.wb_read(reg_run) & 1:
            pass

    async def exec_step(self, opcode):
        if type(opcode) == str:
            opcode = ord(opcode)
        await self.ensure_cpu_stopped()
        await self.wb_write(reg_exec, opcode)
        await self.ensure_cpu_stopped()

    async def push(self, value):
        std_opcodes = "+-|&^<>@=!?2rwxz"
        add_amount = 0
        while (chr(value) in std_opcodes):
            value = value - 1
            add_amount += 1
        await self.exec_step(value)
        if add_amount:
            await self.exec_step(add_amount)
            await self.exec_step('+')

    async def write_progmem(self, addr, value):
        """ 
        Writes a value to progmem by executing an instruction on the CPU.
        """
        if type(value) == str:
            value = ord(value)
        await self.push(value)
        await self.push(addr)
        await self.exec_step('!')


@cocotb.test()
async def test_spell(dut):
    global wishbone
    clock_mhz = 10
    clk_period_ns = round(1/clock_mhz * 1000, 2)
    dut._log.info("input clock = %d MHz, period = %.2f ns" %
                  (clock_mhz, clk_period_ns))

    wishbone_signals = {
        "cyc":  "i_wb_cyc",
        "stb":  "i_wb_stb",
        "we":   "i_wb_we",
        "adr":  "i_wb_addr",
        "datwr": "i_wb_data",
        "datrd": "o_wb_data",
        "ack":  "o_wb_ack"
    }
    wishbone = WishboneMaster(
        dut, "", dut.clock, width=32, timeout=10, signals_dict=wishbone_signals)
    spell = SpellController(dut, wishbone)

    clock = Clock(dut.clock, clk_period_ns, units="ns")
    clock_sig = cocotb.fork(clock.start())
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
