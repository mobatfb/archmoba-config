# ARGUMENTOS: snes super nintendo emulador rom sfc smc python nativo sin dependencias juegos gamepad
"""ARCHMOBA SNES: emulador experimental 65C816/PPU y biblioteca integrados.

No requiere Snes9x, RetroArch, libretro ni modulos pip.
Compatibilidad inicial: ROMs LoROM/HiROM sencillas, PPU modos 0 y 1.
Sin sonido SPC700, prioridad avanzada de sprites, chips especiales ni sincronizacion exacta.
"""
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "ARCHMOBA SNES"
TOOL_DESCRIPTION = "Emulador SNES experimental con nucleo 65C816/PPU integrado en Python sin programas externos."
TOOL_VERSION = "2.0.1"
ROM_EXTS = {".sfc", ".smc", ".fig", ".swc", ".zip"}
INNER_EXTS = ROM_EXTS - {".zip"}
MAX_ZIP_ROM = 32 * 1024 * 1024


def _config_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "ARCHMOBA" / "PTM" / "SNES"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "archmoba" / "ptm" / "snes"


def _unpack_rom(archive, cache_dir):
    """Extrae una ROM compatible de un ZIP, con limite anti-zip-bomb.

    Nunca utiliza rutas internas del ZIP como destinos, evitando path traversal.
    """
    archive = Path(archive)
    with zipfile.ZipFile(archive) as zf:
        members = [item for item in zf.infolist()
                   if not item.is_dir() and Path(item.filename).suffix.lower() in INNER_EXTS]
        if not members:
            raise ValueError("El ZIP no contiene archivos .sfc, .smc, .fig o .swc.")
        members.sort(key=lambda item: (Path(item.filename).suffix.lower() != ".sfc",
                                       item.filename.casefold()))
        member = members[0]
        if member.file_size > MAX_ZIP_ROM:
            raise ValueError("La ROM comprimida supera el limite de 32 MB.")
        stat = archive.stat()
        identity = f"{archive.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{member.filename}"
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        destination = cache_dir / (key + Path(member.filename).suffix.lower())
        if destination.is_file() and destination.stat().st_size == member.file_size:
            return destination
        temp = destination.with_suffix(destination.suffix + ".part")
        try:
            size = 0
            with zf.open(member) as source, temp.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_ZIP_ROM:
                        raise ValueError("ZIP rechazado: contenido demasiado grande.")
                    output.write(chunk)
            os.replace(temp, destination)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return destination


# ====================== ARCHMOBA SNES: motor propio ======================
# Motor experimental SNES/65C816 sin Snes9x, RetroArch, libretro ni paquetes pip.
# Limitaciones: PPU modos 0/1, sin SPC700/audio ni chips de cartucho especiales.
import time

FLAG_C, FLAG_Z, FLAG_I, FLAG_D = 1, 2, 4, 8
FLAG_X, FLAG_M, FLAG_V, FLAG_N = 16, 32, 64, 128
SCREEN_W, SCREEN_H = 256, 224


class UnsupportedROM(ValueError):
    pass


class SnesBus:
    def __init__(self, rom_bytes, save_path=None):
        if len(rom_bytes) % 32768 == 512:
            rom_bytes = rom_bytes[512:]
        if len(rom_bytes) < 32768 or len(rom_bytes) > 16 * 1024 * 1024:
            raise UnsupportedROM('La ROM debe tener entre 32 KB y 16 MB.')
        self.rom = bytes(rom_bytes)
        self.hirom = self._detect_hirom()
        self.save_path = Path(save_path) if save_path else None
        header = (0xFFC0 if self.hirom else 0x7FC0)
        type_code = self.rom[header + 0x16] if header + 0x16 < len(self.rom) else 0
        if type_code in (0x13, 0x14, 0x15, 0x1A, 0x25, 0x34, 0x35, 0x43, 0x45, 0x55, 0xF3, 0xF5):
            raise UnsupportedROM('La ROM requiere un chip adicional no implementado (Super FX, SA-1, DSP u otro).')
        size_exp = self.rom[header + 0x18] if header + 0x18 < len(self.rom) else 0
        sram_size = (1024 << size_exp) if 1 <= size_exp <= 6 else 0
        self.sram = bytearray(min(sram_size, 128 * 1024))
        if self.sram and self.save_path and self.save_path.is_file():
            try:
                raw = self.save_path.read_bytes()
                self.sram[:min(len(raw), len(self.sram))] = raw[:len(self.sram)]
            except OSError:
                pass
        self.wram = bytearray(128 * 1024)
        self.vram = bytearray(65536)
        self.cgram = bytearray(512)
        self.oam = bytearray(544)
        self.ppu_regs = bytearray(256)
        self.io = bytearray(0x200)
        self.dma_regs = bytearray(128)
        self.vaddr = 0
        self.vram_inc_on_high = True
        self.vram_step = 1
        self.cgaddr = 0
        self.cg_second = False
        self.oamaddr = 0
        self.scroll_latch = 0
        self.scroll_x = [0] * 4
        self.scroll_y = [0] * 4
        self.controller = 0
        self.controller_shift = 0
        self.joy_latch = False
        self.nmi_pending = False
        self.nmi_enabled = False
        self.in_vblank = False
        self.frame_number = 0
        self.apu = [0xAA, 0xBB, 0, 0]  # Puertos de arranque simulados; sin sonido.
        self.apu_boot = True
        self.dma_cycles = 0

    def _detect_hirom(self):
        def score(offset, hi):
            if len(self.rom) < offset + 64:
                return -100
            h = self.rom[offset:offset + 64]
            s = 0
            mode = h[0x15]
            if mode & 1 == hi:
                s += 5
            if mode in (0x20, 0x21, 0x30, 0x31, 0x22, 0x23, 0x25, 0x35):
                s += 2
            reset = h[0x3C] | h[0x3D] << 8
            if reset >= 0x8000:
                s += 4
            if (h[0x1C] | h[0x1D] << 8) ^ (h[0x1E] | h[0x1F] << 8) == 0xFFFF:
                s += 4
            if all(32 <= c <= 126 or c == 0 for c in h[:21]):
                s += 1
            return s
        return score(0xFFC0, 1) > score(0x7FC0, 0)

    def _rom_offset(self, bank, addr):
        if self.hirom:
            if bank in range(0x40, 0x7E) or bank >= 0xC0:
                return ((bank & 0x3F) * 65536 + addr) % len(self.rom)
            if addr >= 0x8000:
                return ((bank & 0x3F) * 65536 + addr) % len(self.rom)
        else:
            if addr >= 0x8000 or (0x40 <= bank <= 0x6F) or (0xC0 <= bank <= 0xEF):
                return (((bank & 0x7F) * 32768) + (addr & 0x7FFF)) % len(self.rom)
        return None

    def read(self, address):
        address &= 0xFFFFFF
        bank, addr = address >> 16, address & 0xFFFF
        if bank in (0x7E, 0x7F):
            return self.wram[(bank - 0x7E) * 65536 + addr]
        if bank & 0x7F < 0x40:
            if addr < 0x2000:
                return self.wram[addr]
            if 0x2100 <= addr <= 0x21FF:
                return self.read_ppu(addr & 255)
            if addr == 0x4016:
                val = (self.controller_shift & 1) if not self.joy_latch else (self.controller & 1)
                if not self.joy_latch:
                    self.controller_shift = (self.controller_shift >> 1) | 0x8000
                return val | 0x1C
            if addr == 0x4017:
                return 0x1F
            if 0x4200 <= addr <= 0x421F:
                if addr == 0x4210:
                    result = (0x80 if self.nmi_pending else 0) | 2
                    self.nmi_pending = False
                    return result
                if addr == 0x4212:
                    return (0x80 if self.in_vblank else 0)
                if 0x4218 <= addr <= 0x421F:
                    return (self.controller >> (8 * ((addr - 0x4218) % 2))) & 255 if addr <= 0x4219 else 0
                return self.io[addr - 0x4200]
            if 0x4300 <= addr <= 0x437F:
                return self.dma_regs[addr - 0x4300]
        if not self.hirom and bank in range(0x70, 0x7E) or (not self.hirom and bank >= 0xF0):
            if addr < 0x8000 and self.sram:
                return self.sram[((bank & 15) * 32768 + addr) % len(self.sram)]
        if self.hirom and bank in range(0x20, 0x40) and 0x6000 <= addr < 0x8000 and self.sram:
            return self.sram[((bank & 31) * 8192 + addr - 0x6000) % len(self.sram)]
        offset = self._rom_offset(bank, addr)
        return self.rom[offset] if offset is not None else 0

    def write(self, address, value):
        address &= 0xFFFFFF
        value &= 255
        bank, addr = address >> 16, address & 0xFFFF
        if bank in (0x7E, 0x7F):
            self.wram[(bank - 0x7E) * 65536 + addr] = value
            return
        if bank & 0x7F < 0x40:
            if addr < 0x2000:
                self.wram[addr] = value
                return
            if 0x2100 <= addr <= 0x21FF:
                self.write_ppu(addr & 255, value)
                return
            if addr == 0x4016:
                if value & 1:
                    self.joy_latch = True
                    self.controller_shift = self.controller
                elif self.joy_latch:
                    self.joy_latch = False
                    self.controller_shift = self.controller
                return
            if 0x4200 <= addr <= 0x421F:
                self.io[addr - 0x4200] = value
                if addr == 0x4200:
                    self.nmi_enabled = bool(value & 0x80)
                elif addr == 0x4202:
                    pass
                elif addr == 0x4203:
                    prod = self.io[2] * value
                    self.io[0x16] = prod & 255
                    self.io[0x17] = (prod >> 8) & 255
                elif addr == 0x4206:
                    dividend = self.io[4] | self.io[5] << 8
                    q, r = (divmod(dividend, value) if value else (65535, dividend))
                    self.io[0x14] = q & 255
                    self.io[0x15] = (q >> 8) & 255
                    self.io[0x16] = r & 255
                    self.io[0x17] = (r >> 8) & 255
                elif addr == 0x420B:
                    self._dma(value)
                return
            if 0x4300 <= addr <= 0x437F:
                self.dma_regs[addr - 0x4300] = value
                return
        if not self.hirom and (0x70 <= bank <= 0x7D or 0xF0 <= bank <= 0xFF):
            if addr < 0x8000 and self.sram:
                self.sram[((bank & 15) * 32768 + addr) % len(self.sram)] = value
        if self.hirom and 0x20 <= bank <= 0x3F and 0x6000 <= addr < 0x8000 and self.sram:
            self.sram[((bank & 31) * 8192 + addr - 0x6000) % len(self.sram)] = value

    def read16(self, addr):
        return self.read(addr) | (self.read((addr & 0xFF0000) | ((addr + 1) & 0xFFFF)) << 8)

    def read24(self, addr):
        return self.read16(addr) | (self.read((addr & 0xFF0000) | ((addr + 2) & 0xFFFF)) << 16)

    def write16(self, addr, value):
        self.write(addr, value)
        self.write((addr & 0xFF0000) | ((addr + 1) & 0xFFFF), value >> 8)

    def write_ppu(self, reg, value):
        self.ppu_regs[reg] = value
        if reg == 0x15:
            self.vram_inc_on_high = bool(value & 0x80)
            self.vram_step = (1, 32, 128, 128)[value & 3]
        elif reg == 0x16:
            self.vaddr = (self.vaddr & 0xFF00) | value
        elif reg == 0x17:
            self.vaddr = (self.vaddr & 255) | (value << 8)
        elif reg in (0x18, 0x19):
            self.vram[(self.vaddr * 2 + (reg & 1)) & 0xFFFF] = value
            if (reg == 0x19) == self.vram_inc_on_high:
                self.vaddr = (self.vaddr + self.vram_step) & 0xFFFF
        elif reg == 0x21:
            self.cgaddr = value * 2
            self.cg_second = False
        elif reg == 0x22:
            self.cgram[self.cgaddr % 512] = value
            self.cgaddr = (self.cgaddr + 1) % 512
        elif reg == 0x02:
            self.oamaddr = (self.oamaddr & 0x100) | value
        elif reg == 0x03:
            self.oamaddr = (self.oamaddr & 255) | ((value & 1) << 8)
        elif reg == 0x04:
            self.oam[self.oamaddr % len(self.oam)] = value
            self.oamaddr = (self.oamaddr + 1) % len(self.oam)
        elif 0x0D <= reg <= 0x14:
            bg = (reg - 0x0D) // 2
            is_vertical = (reg - 0x0D) & 1
            old = self.scroll_latch
            new = ((value << 8) | old) & 0x3FF
            (self.scroll_y if is_vertical else self.scroll_x)[bg] = new
            self.scroll_latch = value
        elif 0x40 <= reg <= 0x43:
            self.apu[reg - 0x40] = value
            if reg == 0x40 and value == 0xCC:
                self.apu_boot = False

    def read_ppu(self, reg):
        if 0x40 <= reg <= 0x43:
            return self.apu[reg - 0x40]
        if reg in (0x39, 0x3A):
            val = self.vram[(self.vaddr * 2 + (reg & 1)) & 0xFFFF]
            if (reg == 0x3A) == self.vram_inc_on_high:
                self.vaddr = (self.vaddr + self.vram_step) & 0xFFFF
            return val
        if reg == 0x3B:
            val = self.cgram[self.cgaddr % 512]
            self.cgaddr = (self.cgaddr + 1) % 512
            return val
        if reg == 0x3F:
            return 0x03
        return self.ppu_regs[reg]

    def _dma(self, mask):
        for ch in range(8):
            if not (mask & (1 << ch)):
                continue
            off = ch * 16
            ctrl = self.dma_regs[off]
            dest = self.dma_regs[off + 1]
            src = self.dma_regs[off + 2] | self.dma_regs[off + 3] << 8
            bank = self.dma_regs[off + 4]
            count = self.dma_regs[off + 5] | self.dma_regs[off + 6] << 8
            count = count or 65536
            mode = ctrl & 7
            patterns = ((0,), (0, 1), (0, 0), (0, 0, 1, 1), (0, 1, 2, 3), (0, 1, 0, 1), (0, 0), (0, 0, 1, 1))
            offsets = patterns[mode]
            for i in range(count):
                reg = 0x2100 + ((dest + offsets[i % len(offsets)]) & 255)
                addr = bank << 16 | src
                if ctrl & 0x80:
                    self.write(addr, self.read(reg))
                else:
                    self.write(reg, self.read(addr))
                if not ctrl & 0x08:
                    src = (src - 1 if ctrl & 0x10 else src + 1) & 0xFFFF
            self.dma_regs[off + 2] = src & 255
            self.dma_regs[off + 3] = src >> 8
            self.dma_regs[off + 5] = self.dma_regs[off + 6] = 0
            self.dma_cycles += count * 8

    def end_frame(self):
        self.frame_number += 1

    def save_sram(self):
        if not self.sram or not self.save_path:
            return
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.save_path.with_suffix('.tmp')
        tmp.write_bytes(self.sram)
        os.replace(tmp, self.save_path)


# Tabla de las 256 instrucciones oficiales WDC 65C816.
# addr: dp,dpx,dpy,abs,absx,absy,long,longx,idx,idy,idp,idl,ily,sr,sry
# otros: immM,immX,imm8,imm16,rel,rel16,ind,indx,indl,acc,imp,blk
_OPCODE_ROWS = '''
BRK:sig ORA:idx COP:sig ORA:sr TSB:dp ORA:dp ASL:dp ORA:idl PHP:imp ORA:immM ASL:acc PHD:imp TSB:abs ORA:abs ASL:abs ORA:long
BPL:rel ORA:idy ORA:idp ORA:sry TRB:dp ORA:dpx ASL:dpx ORA:ily CLC:imp ORA:absy INC:acc TCS:imp TRB:abs ORA:absx ASL:absx ORA:longx
JSR:abs AND:idx JSL:long AND:sr BIT:dp AND:dp ROL:dp AND:idl PLP:imp AND:immM ROL:acc PLD:imp BIT:abs AND:abs ROL:abs AND:long
BMI:rel AND:idy AND:idp AND:sry BIT:dpx AND:dpx ROL:dpx AND:ily SEC:imp AND:absy DEC:acc TSC:imp BIT:absx AND:absx ROL:absx AND:longx
RTI:imp EOR:idx WDM:imm8 EOR:sr MVP:blk EOR:dp LSR:dp EOR:idl PHA:imp EOR:immM LSR:acc PHK:imp JMP:abs EOR:abs LSR:abs EOR:long
BVC:rel EOR:idy EOR:idp EOR:sry MVN:blk EOR:dpx LSR:dpx EOR:ily CLI:imp EOR:absy PHY:imp TCD:imp JML:long EOR:absx LSR:absx EOR:longx
RTS:imp ADC:idx PER:rel16 ADC:sr STZ:dp ADC:dp ROR:dp ADC:idl PLA:imp ADC:immM ROR:acc RTL:imp JMP:ind ADC:abs ROR:abs ADC:long
BVS:rel ADC:idy ADC:idp ADC:sry STZ:dpx ADC:dpx ROR:dpx ADC:ily SEI:imp ADC:absy PLY:imp TDC:imp JMP:indx ADC:absx ROR:absx ADC:longx
BRA:rel STA:idx BRL:rel16 STA:sr STY:dp STA:dp STX:dp STA:idl DEY:imp BIT:immM TXA:imp PHB:imp STY:abs STA:abs STX:abs STA:long
BCC:rel STA:idy STA:idp STA:sry STY:dpx STA:dpx STX:dpy STA:ily TYA:imp STA:absy TXS:imp TXY:imp STZ:abs STA:absx STZ:absx STA:longx
LDY:immX LDA:idx LDX:immX LDA:sr LDY:dp LDA:dp LDX:dp LDA:idl TAY:imp LDA:immM TAX:imp PLB:imp LDY:abs LDA:abs LDX:abs LDA:long
BCS:rel LDA:idy LDA:idp LDA:sry LDY:dpx LDA:dpx LDX:dpy LDA:ily CLV:imp LDA:absy TSX:imp TYX:imp LDY:absx LDA:absx LDX:absy LDA:longx
CPY:immX CMP:idx REP:imm8 CMP:sr CPY:dp CMP:dp DEC:dp CMP:idl INY:imp CMP:immM DEX:imp WAI:imp CPY:abs CMP:abs DEC:abs CMP:long
BNE:rel CMP:idy CMP:idp CMP:sry PEI:idp CMP:dpx DEC:dpx CMP:ily CLD:imp CMP:absy PHX:imp STP:imp JML:indl CMP:absx DEC:absx CMP:longx
CPX:immX SBC:idx SEP:imm8 SBC:sr CPX:dp SBC:dp INC:dp SBC:idl INX:imp SBC:immM NOP:imp XBA:imp CPX:abs SBC:abs INC:abs SBC:long
BEQ:rel SBC:idy SBC:idp SBC:sry PEA:imm16 SBC:dpx INC:dpx SBC:ily SED:imp SBC:absy PLX:imp XCE:imp JSR:indx SBC:absx INC:absx SBC:longx
'''
OPCODES = [tuple(op.split(':')) for op in _OPCODE_ROWS.split()]
assert len(OPCODES) == 256


class CPU65816:
    def __init__(self, bus):
        self.bus = bus
        self.a = self.x = self.y = self.d = self.db = self.pb = 0
        self.sp = 0x1FF
        self.p = FLAG_M | FLAG_X | FLAG_I
        self.e = True
        self.pc = bus.read16(0xFFFC)
        self.cycles = 0
        self.waiting = False
        self.stopped = False

    def am(self):
        return 8 if self.p & FLAG_M else 16

    def ix(self):
        return 8 if self.p & FLAG_X else 16

    def fetch8(self):
        v = self.bus.read((self.pb << 16) | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        return self.fetch8() | self.fetch8() << 8

    def fetch24(self):
        return self.fetch16() | self.fetch8() << 16

    def push8(self, v):
        self.bus.write(self.sp, v)
        self.sp = (self.sp - 1) & (0xFF if self.e else 0xFFFF)
        if self.e:
            self.sp |= 0x100

    def pop8(self):
        self.sp = (self.sp + 1) & (0xFF if self.e else 0xFFFF)
        if self.e:
            self.sp |= 0x100
        return self.bus.read(self.sp)

    def push16(self, v):
        self.push8(v >> 8)
        self.push8(v)

    def pop16(self):
        return self.pop8() | self.pop8() << 8

    def nz(self, v, width):
        mask = (1 << width) - 1
        self.p = (self.p & ~(FLAG_Z | FLAG_N)) | (FLAG_Z if not (v & mask) else 0) | (FLAG_N if v & (1 << (width - 1)) else 0)
        return v & mask

    def _width(self, op):
        return self.ix() if op in ('LDX', 'LDY', 'STX', 'STY', 'CPX', 'CPY') else self.am()

    def _address(self, mode):
        b = self.bus
        if mode == 'dp':
            return (self.d + self.fetch8()) & 0xFFFF
        if mode == 'dpx':
            return (self.d + self.fetch8() + self.x) & 0xFFFF
        if mode == 'dpy':
            return (self.d + self.fetch8() + self.y) & 0xFFFF
        if mode == 'abs':
            return (self.db << 16) | self.fetch16()
        if mode == 'absx':
            return (self.db << 16) | ((self.fetch16() + self.x) & 0xFFFF)
        if mode == 'absy':
            return (self.db << 16) | ((self.fetch16() + self.y) & 0xFFFF)
        if mode == 'long':
            return self.fetch24()
        if mode == 'longx':
            return (self.fetch24() + self.x) & 0xFFFFFF
        if mode == 'sr':
            return (self.sp + self.fetch8()) & 0xFFFF
        if mode == 'idx':
            ptr = (self.d + self.fetch8() + self.x) & 0xFFFF
            return (self.db << 16) | b.read16(ptr)
        if mode in ('idy', 'idp', 'idl', 'ily'):
            ptr = (self.d + self.fetch8()) & 0xFFFF
            if mode in ('idl', 'ily'):
                addr = b.read24(ptr)
                return (addr + (self.y if mode == 'ily' else 0)) & 0xFFFFFF
            return (self.db << 16) | ((b.read16(ptr) + (self.y if mode == 'idy' else 0)) & 0xFFFF)
        if mode == 'sry':
            ptr = (self.sp + self.fetch8()) & 0xFFFF
            return (self.db << 16) | ((b.read16(ptr) + self.y) & 0xFFFF)
        raise RuntimeError('Modo no implementado: ' + mode)

    def _operand(self, mode, width):
        if mode in ('immM', 'immX'):
            return None, self.fetch8() if width == 8 else self.fetch16()
        addr = self._address(mode)
        return addr, self.bus.read(addr) if width == 8 else self.bus.read16(addr)

    def _write(self, addr, value, width):
        if width == 8:
            self.bus.write(addr, value)
        else:
            self.bus.write16(addr, value)

    def _get(self, reg, width):
        return getattr(self, reg) & ((1 << width) - 1)

    def _set(self, reg, val, width):
        val = self.nz(val, width)
        if reg == 'a' and width == 8:
            self.a = (self.a & 0xFF00) | val
        else:
            setattr(self, reg, val)

    def _status(self, value):
        self.p = value & 255
        if self.e:
            self.p |= FLAG_M | FLAG_X
        if self.p & FLAG_X:
            self.x &= 255
            self.y &= 255

    def _interrupt(self, vector, break_flag=False):
        if not self.e:
            self.push8(self.pb)
        self.push16(self.pc)
        self.push8((self.p | (0x10 if break_flag else 0)) if self.e else self.p)
        self.p = (self.p | FLAG_I) & ~FLAG_D
        self.pb = 0
        self.pc = self.bus.read16(vector)
        self.waiting = False

    def nmi(self):
        if self.bus.nmi_enabled:
            self._interrupt(0xFFFA if self.e else 0xFFEA)
        elif self.waiting:
            self.waiting = False

    def _adc(self, v, width, subtract=False):
        mask = (1 << width) - 1
        a = self.a & mask
        carry = 1 if self.p & FLAG_C else 0
        if subtract:
            raw = a + (v ^ mask) + carry
            overflow = bool(((a ^ v) & (a ^ raw)) & (1 << (width - 1)))
        else:
            raw = a + v + carry
            overflow = bool((~(a ^ v) & (a ^ raw)) & (1 << (width - 1)))
        if self.p & FLAG_D:
            result = 0
            c = carry
            for shift in range(0, width, 4):
                av, bv = (a >> shift) & 15, (v >> shift) & 15
                if subtract:
                    digit = av - bv - (1 - c)
                    c = 1 if digit >= 0 else 0
                    if digit < 0:
                        digit += 10
                else:
                    digit = av + bv + c
                    c = 1 if digit <= 9 else 0
                    if digit > 9:
                        digit -= 10
                result |= (digit & 15) << shift
            carry_out = c
        else:
            result = raw & mask
            carry_out = 1 if raw > mask else 0
        self.p = (self.p & ~(FLAG_C | FLAG_V)) | (FLAG_C if carry_out else 0) | (FLAG_V if overflow else 0)
        self._set('a', result, width)

    def step(self):
        if self.stopped or self.waiting:
            return 0
        opbyte = self.fetch8()
        op, mode = OPCODES[opbyte]
        self.cycles += 4
        width = self._width(op)
        mask = (1 << width) - 1
        if op in ('LDA', 'LDX', 'LDY', 'ORA', 'AND', 'EOR', 'ADC', 'SBC', 'CMP', 'CPX', 'CPY', 'BIT'):
            addr, v = self._operand(mode, width)
            if op in ('LDA', 'LDX', 'LDY'):
                self._set({'LDA': 'a', 'LDX': 'x', 'LDY': 'y'}[op], v, width)
            elif op in ('ORA', 'AND', 'EOR'):
                a = self.a & mask
                self._set('a', {'ORA': a | v, 'AND': a & v, 'EOR': a ^ v}[op], width)
            elif op in ('ADC', 'SBC'):
                self._adc(v, width, op == 'SBC')
            elif op in ('CMP', 'CPX', 'CPY'):
                a = self._get({'CMP': 'a', 'CPX': 'x', 'CPY': 'y'}[op], width)
                self.p = (self.p & ~FLAG_C) | (FLAG_C if a >= v else 0)
                self.nz(a - v, width)
            elif op == 'BIT':
                self.p = (self.p & ~FLAG_Z) | (FLAG_Z if not (self.a & v & mask) else 0)
                if mode != 'immM':
                    self.p = (self.p & ~(FLAG_N | FLAG_V)) | (v & (FLAG_N | FLAG_V) if width == 8 else ((v >> 8) & (FLAG_N | FLAG_V)))
            return 4
        if op in ('STA', 'STX', 'STY', 'STZ'):
            addr = self._address(mode)
            self._write(addr, 0 if op == 'STZ' else self._get({'STA': 'a', 'STX': 'x', 'STY': 'y'}.get(op, 'a'), width), width)
            return 4
        if op in ('ASL', 'LSR', 'ROL', 'ROR', 'INC', 'DEC', 'TSB', 'TRB'):
            if mode == 'acc':
                v, addr = self.a & mask, None
            else:
                addr, v = self._operand(mode, width)
            if op in ('TSB', 'TRB'):
                self.p = (self.p & ~FLAG_Z) | (FLAG_Z if not (self.a & v & mask) else 0)
                out = v | (self.a & mask) if op == 'TSB' else v & ~(self.a & mask)
            elif op == 'INC':
                out = self.nz(v + 1, width)
            elif op == 'DEC':
                out = self.nz(v - 1, width)
            else:
                carry = 1 if self.p & FLAG_C else 0
                if op in ('ASL', 'ROL'):
                    c = bool(v & (1 << (width - 1)))
                    out = (v << 1) | (carry if op == 'ROL' else 0)
                else:
                    c = bool(v & 1)
                    out = (v >> 1) | ((carry << (width - 1)) if op == 'ROR' else 0)
                self.p = (self.p & ~FLAG_C) | (FLAG_C if c else 0)
                out = self.nz(out, width)
            if addr is None:
                self.a = (self.a & 0xFF00 | out & 255) if width == 8 else out & 65535
            else:
                self._write(addr, out, width)
            return 4
        if op in ('BPL', 'BMI', 'BVC', 'BVS', 'BCC', 'BCS', 'BNE', 'BEQ', 'BRA', 'BRL'):
            rel = self.fetch16() if op == 'BRL' else self.fetch8()
            if rel & (0x8000 if op == 'BRL' else 0x80):
                rel -= 0x10000 if op == 'BRL' else 0x100
            flag, expected = {'BPL': (FLAG_N, False), 'BMI': (FLAG_N, True),
                              'BVC': (FLAG_V, False), 'BVS': (FLAG_V, True),
                              'BCC': (FLAG_C, False), 'BCS': (FLAG_C, True),
                              'BNE': (FLAG_Z, False), 'BEQ': (FLAG_Z, True)}.get(op, (0, True))
            if not flag or bool(self.p & flag) == expected:
                self.pc = (self.pc + rel) & 0xFFFF
            return 4
        if op in ('JMP', 'JML', 'JSR', 'JSL'):
            if mode == 'abs':
                addr = (self.pb << 16) | self.fetch16()
            elif mode == 'long':
                addr = self.fetch24()
            elif mode in ('ind', 'indl', 'indx'):
                ptr = self.fetch16()
                if mode == 'indx':
                    ptr = (ptr + self.x) & 0xFFFF
                addr = (self.pb << 16) | ptr
                addr = self.bus.read24(addr) if mode == 'indl' else ((self.pb << 16) | self.bus.read16(addr))
            else:
                raise RuntimeError('Salto no implementado: ' + mode)
            if op == 'JSL':
                self.push8(self.pb)
                self.push16((self.pc - 1) & 0xFFFF)
            elif op == 'JSR':
                self.push16((self.pc - 1) & 0xFFFF)
            self.pc = addr & 0xFFFF
            self.pb = (addr >> 16) & 255
            return 4
        if op in ('RTS', 'RTL', 'RTI'):
            if op == 'RTI':
                self._status(self.pop8())
                self.pc = self.pop16()
                if not self.e:
                    self.pb = self.pop8()
            else:
                self.pc = (self.pop16() + 1) & 0xFFFF
                if op == 'RTL':
                    self.pb = self.pop8()
            return 4
        if op in ('BRK', 'COP'):
            self.fetch8()
            self._interrupt((0xFFFE if op == 'BRK' else 0xFFF4) if self.e else
                            (0xFFE6 if op == 'BRK' else 0xFFE4), True)
            return 4
        if op in ('REP', 'SEP'):
            value = self.fetch8()
            self._status((self.p & ~value) if op == 'REP' else (self.p | value))
            return 4
        if op in ('CLC', 'SEC', 'CLI', 'SEI', 'CLD', 'SED', 'CLV'):
            bit = {'CLC': FLAG_C, 'SEC': FLAG_C, 'CLI': FLAG_I, 'SEI': FLAG_I,
                   'CLD': FLAG_D, 'SED': FLAG_D, 'CLV': FLAG_V}[op]
            if op.startswith('CL'):
                self.p &= ~bit
            else:
                self.p |= bit
            return 4
        if op in ('INX', 'DEX', 'INY', 'DEY'):
            reg = 'x' if op.endswith('X') else 'y'
            w = self.ix()
            self._set(reg, self._get(reg, w) + (1 if op.startswith('IN') else -1), w)
            return 4
        if op in ('TAX', 'TAY', 'TXA', 'TYA', 'TXY', 'TYX', 'TSX', 'TXS', 'TCS', 'TSC', 'TCD', 'TDC'):
            src, dst = {'TAX': ('a', 'x'), 'TAY': ('a', 'y'), 'TXA': ('x', 'a'),
                        'TYA': ('y', 'a'), 'TXY': ('x', 'y'), 'TYX': ('y', 'x'),
                        'TSX': ('sp', 'x'), 'TXS': ('x', 'sp'), 'TCS': ('a', 'sp'),
                        'TSC': ('sp', 'a'), 'TCD': ('a', 'd'), 'TDC': ('d', 'a')}[op]
            w = self.ix() if dst in ('x', 'y') else (16 if dst in ('d', 'sp') or op in ('TSC', 'TDC') else self.am())
            val = getattr(self, src)
            if dst == 'sp':
                self.sp = ((0x100 | (val & 255)) if self.e else (val & 65535))
            elif dst == 'd':
                self.d = self.nz(val, 16)
            else:
                self._set(dst, val, w)
            return 4
        if op in ('PHA', 'PLA', 'PHX', 'PLX', 'PHY', 'PLY', 'PHP', 'PLP', 'PHB', 'PLB', 'PHD', 'PLD', 'PHK'):
            if op.startswith('PH'):
                if op == 'PHP':
                    self.push8(self.p)
                elif op == 'PHB':
                    self.push8(self.db)
                elif op == 'PHK':
                    self.push8(self.pb)
                elif op == 'PHD':
                    self.push16(self.d)
                else:
                    reg = {'PHA': 'a', 'PHX': 'x', 'PHY': 'y'}[op]
                    w = self.am() if reg == 'a' else self.ix()
                    (self.push8 if w == 8 else self.push16)(getattr(self, reg))
            else:
                if op == 'PLP':
                    self._status(self.pop8())
                elif op == 'PLB':
                    self.db = self.nz(self.pop8(), 8)
                elif op == 'PLD':
                    self.d = self.nz(self.pop16(), 16)
                else:
                    reg = {'PLA': 'a', 'PLX': 'x', 'PLY': 'y'}[op]
                    w = self.am() if reg == 'a' else self.ix()
                    self._set(reg, self.pop8() if w == 8 else self.pop16(), w)
            return 4
        if op in ('PEA', 'PEI', 'PER'):
            if op == 'PEA':
                value = self.fetch16()
            elif op == 'PEI':
                value = self.bus.read16((self.d + self.fetch8()) & 0xFFFF)
            else:
                rel = self.fetch16()
                value = (self.pc + (rel - 65536 if rel & 32768 else rel)) & 65535
            self.push16(value)
            return 4
        if op in ('MVN', 'MVP'):
            dest, src = self.fetch8(), self.fetch8()
            self.db = dest
            self.bus.write((dest << 16) | self.y, self.bus.read((src << 16) | self.x))
            delta = 1 if op == 'MVN' else -1
            self.x = (self.x + delta) & (255 if self.ix() == 8 else 65535)
            self.y = (self.y + delta) & (255 if self.ix() == 8 else 65535)
            self.a = (self.a - 1) & 65535
            if self.a != 65535:
                self.pc = (self.pc - 3) & 65535
            return 4
        if op == 'XBA':
            self.a = ((self.a & 255) << 8) | (self.a >> 8)
            self.nz(self.a & 255, 8)
            return 4
        if op == 'XCE':
            old_c = bool(self.p & FLAG_C)
            self.p = (self.p & ~FLAG_C) | (FLAG_C if self.e else 0)
            self.e = old_c
            self._status(self.p)
            if self.e:
                self.sp = 0x100 | (self.sp & 255)
            return 4
        if op == 'WAI':
            self.waiting = True
            return 4
        if op == 'STP':
            self.stopped = True
            return 4
        if op == 'WDM':
            self.fetch8()
            return 4
        if op == 'NOP':
            return 4
        raise RuntimeError(f'Instruccion sin implementar {opbyte:02X}: {op}')


class SnesPPU:
    """PPU parcial: fondos tileados modo 0/1, paletas CGRAM, sin sonido."""
    def __init__(self, bus):
        self.bus = bus
        self.frame = 0

    def _sprite_pixels(self, palette):
        """Sprites OBJ 4bpp de 8/16/32/64 px, sin prioridad exacta de hardware."""
        b = self.bus
        obsel = b.ppu_regs[1]
        sizes = ((8, 16), (8, 32), (8, 64), (16, 32),
                 (16, 64), (32, 64), (16, 32), (16, 32))
        small, large = sizes[(obsel >> 5) & 7]
        base = (obsel & 7) * 0x4000
        pixels = [None] * (SCREEN_W * SCREEN_H)
        # OAM 0 tiene prioridad sobre OAM 127.
        for sprite in range(127, -1, -1):
            off = sprite * 4
            x = b.oam[off]
            y = b.oam[off + 1]
            tile = b.oam[off + 2]
            attr = b.oam[off + 3]
            high = b.oam[512 + sprite // 4]
            extra = (high >> ((sprite % 4) * 2)) & 3
            x |= (extra & 1) << 8
            if x >= 256:
                x -= 512
            size = large if extra & 2 else small
            tile |= (attr & 1) << 8
            pal = (attr >> 1) & 7
            hflip, vflip = bool(attr & 0x40), bool(attr & 0x80)
            for yy in range(size):
                py = (y + yy) & 255
                if py >= SCREEN_H:
                    continue
                local_y = size - 1 - yy if vflip else yy
                tile_y = local_y // 8
                row = local_y & 7
                for xx in range(size):
                    px = x + xx
                    if not 0 <= px < SCREEN_W:
                        continue
                    local_x = size - 1 - xx if hflip else xx
                    tile_x = local_x // 8
                    col = local_x & 7
                    tile_no = ((tile & 0x1F0) | ((tile + tile_x) & 15)) + tile_y * 16
                    addr = (base + (tile_no & 511) * 32 + row * 2) & 65535
                    bit = 7 - col
                    idx = ((b.vram[addr] >> bit) & 1)
                    idx |= ((b.vram[(addr + 1) & 65535] >> bit) & 1) << 1
                    idx |= ((b.vram[(addr + 16) & 65535] >> bit) & 1) << 2
                    idx |= ((b.vram[(addr + 17) & 65535] >> bit) & 1) << 3
                    if idx:
                        pixels[py * SCREEN_W + px] = palette[128 + pal * 16 + idx]
        return pixels

    def render(self):
        b = self.bus
        regs = b.ppu_regs
        forced_blank = bool(regs[0] & 0x80)
        brightness = regs[0] & 15
        mode = regs[5] & 7
        enabled = regs[0x2C]
        out = bytearray(SCREEN_W * SCREEN_H * 3)
        if forced_blank or brightness == 0:
            return bytes(out)
        palette = []
        for i in range(256):
            raw = b.cgram[i * 2] | b.cgram[i * 2 + 1] << 8
            palette.append(((raw & 31) * 255 // 31 * brightness // 15,
                            ((raw >> 5) & 31) * 255 // 31 * brightness // 15,
                            ((raw >> 10) & 31) * 255 // 31 * brightness // 15))
        back = palette[0]
        bg_types = ([2, 2, 2, 2] if mode == 0 else [4, 4, 2, 0])
        layers = [i for i in range(4) if enabled & (1 << i) and bg_types[i]] if mode in (0, 1) else []
        sprites = self._sprite_pixels(palette) if enabled & 0x10 else None
        # Orden simplificado de prioridad: BG1 encima de BG2, BG3, BG4.
        tile_cache = {}
        for y in range(SCREEN_H):
            for x in range(SCREEN_W):
                color = back
                for bg in reversed(layers):
                    depth = bg_types[bg]
                    scrollx = b.scroll_x[bg]
                    scrolly = b.scroll_y[bg]
                    xx, yy = (x + scrollx) & 1023, (y + scrolly) & 1023
                    tx, ty = xx >> 3, yy >> 3
                    sc = regs[7 + bg]
                    size_x = 64 if sc & 1 else 32
                    size_y = 64 if sc & 2 else 32
                    tx %= size_x
                    ty %= size_y
                    map_base = (sc & 0xFC) * 0x100
                    screen_index = (tx // 32) + (ty // 32) * (2 if size_x == 64 else 1)
                    tile_addr = (map_base + screen_index * 0x800 + (ty % 32 * 32 + tx % 32) * 2) & 0xFFFF
                    entry = b.vram[tile_addr] | b.vram[(tile_addr + 1) & 65535] << 8
                    tile = entry & 1023
                    char_reg = regs[0x0B + (bg // 2)]
                    char_base = ((char_reg >> (4 if bg & 1 else 0)) & 15) * 0x1000
                    tile_base = (char_base + tile * (16 if depth == 2 else 32)) & 65535
                    px = (7 - (xx & 7)) if entry & 0x4000 else (xx & 7)
                    py = (7 - (yy & 7)) if entry & 0x8000 else (yy & 7)
                    key = (tile_base, depth, py, px)
                    index = tile_cache.get(key)
                    if index is None:
                        offset = (tile_base + py * 2) & 65535
                        bit = 7 - px
                        index = ((b.vram[offset] >> bit) & 1) | (((b.vram[(offset + 1) & 65535] >> bit) & 1) << 1)
                        if depth == 4:
                            index |= ((b.vram[(offset + 16) & 65535] >> bit) & 1) << 2
                            index |= ((b.vram[(offset + 17) & 65535] >> bit) & 1) << 3
                        tile_cache[key] = index
                    if index:
                        palette_base = (bg * 32 if mode == 0 else 0)
                        color = palette[(palette_base + ((entry >> 10) & 7) * (4 if depth == 2 else 16) + index) & 255]
                if sprites is not None:
                    sprite = sprites[y * SCREEN_W + x]
                    if sprite is not None:
                        color = sprite
                off = (y * SCREEN_W + x) * 3
                out[off] = color[0]
                out[off + 1] = color[1]
                out[off + 2] = color[2]
        return bytes(out)


class NativeSnesMachine:
    def __init__(self, rom, save_path=None):
        self.bus = SnesBus(rom, save_path)
        self.cpu = CPU65816(self.bus)
        self.ppu = SnesPPU(self.bus)
        if self.cpu.pc < 0x8000:
            raise UnsupportedROM('Vector de arranque invalido: la ROM no parece SNES LoROM/HiROM.')
        self.frame_count = 0

    def frame(self, stop_event=None):
        b = self.bus
        b.in_vblank = False
        b.nmi_pending = False
        cycles = 0
        # Ciclos aproximados por cuadro; no reproduce tiempos exactos de hardware.
        while cycles < 32000:
            if stop_event is not None and stop_event.is_set():
                break
            if cycles >= 26000 and not b.in_vblank:
                b.in_vblank = True
                b.nmi_pending = True
                self.cpu.nmi()
            if self.cpu.stopped:
                break
            if self.cpu.waiting:
                # WAI aguarda al proximo VBlank, no detiene el motor.
                if not b.in_vblank:
                    cycles = 26000
                    continue
                break
            cycles += self.cpu.step() + b.dma_cycles
            b.dma_cycles = 0
        b.end_frame()
        self.frame_count += 1
        return self.ppu.render()

    def save(self):
        self.bus.save_sram()


class NativeSnesWindow(tk.Toplevel):
    """Ventana Tk para el motor 65C816 interno, sin procesos ni emuladores externos."""
    KEY_BITS = {
        'z': 0, 'a': 1, 'Shift_L': 2, 'Shift_R': 2,
        'Return': 3, 'Up': 4, 'Down': 5, 'Left': 6, 'Right': 7,
        'x': 8, 's': 9, 'q': 10, 'w': 11,
    }

    def __init__(self, parent, rom_path, rom_bytes, save_path, fullscreen=False, on_closed=None):
        super().__init__(parent)
        self.title('ARCHMOBA SNES · ' + Path(rom_path).stem)
        self.configure(bg='#101827')
        self.geometry('590x550')
        self.minsize(330, 300)
        # Independent floating window, always above the PTM main window.
        try:
            host = parent.winfo_toplevel()
            self.transient(host)
            host.update_idletasks()
            x = host.winfo_rootx() + max(20, (host.winfo_width() - 590) // 2)
            y = host.winfo_rooty() + max(20, (host.winfo_height() - 550) // 2)
            self.geometry(f'590x550+{x}+{y}')
        except tk.TclError:
            pass
        self.machine = NativeSnesMachine(rom_bytes, save_path)
        self._stopping = threading.Event()
        self._paused = threading.Event()
        self._frames = queue.Queue(maxsize=2)
        self._pressed = set()
        self._image = None
        self._photo_item = None
        self._closed = False
        self._on_closed = on_closed
        self._fullscreen = False
        self._frame_displayed = 0
        self._last_fps_time = time.monotonic()
        self._fps = 0
        self._status = tk.StringVar(value='Motor integrado · audio no implementado')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, width=512, height=448, bg='#000000',
                                bd=0, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew', padx=9, pady=9)
        self.canvas.bind('<Configure>', self._resize)
        footer = ttk.Frame(self, padding=(9, 0, 9, 9))
        footer.grid(row=1, column=0, sticky='ew')
        ttk.Button(footer, text='Pausa / Continuar', command=self.toggle_pause).pack(side='left')
        ttk.Button(footer, text='⛶ Pantalla completa', command=self.toggle_fullscreen).pack(side='left', padx=5)
        ttk.Button(footer, text='✕ Cerrar juego', command=self.close, width=15).pack(side='right')
        ttk.Label(footer, textvariable=self._status).pack(side='right', padx=(5, 12))
        self.bind('<KeyPress>', self._key_down)
        self.bind('<KeyRelease>', self._key_up)
        self.bind('<FocusOut>', self._focus_out)
        self.bind('<F11>', lambda _event: self.toggle_fullscreen())
        self.bind('<Escape>', self._escape)
        self.bind('<Control-w>', lambda _event: self.close())
        self.protocol('WM_DELETE_WINDOW', self.close)
        self._thread = threading.Thread(target=self._run, daemon=True, name='ARCHMOBA-SNES-CPU')
        self._thread.start()
        self.after(50, self._pump)
        if fullscreen:
            self.after(100, self.toggle_fullscreen)
        self.after(130, self._focus_floating)

    def _focus_floating(self):
        if self._closed:
            return
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def _run(self):
        try:
            while not self._stopping.is_set():
                if self._paused.is_set():
                    time.sleep(0.03)
                    continue
                start = time.monotonic()
                pixels = self.machine.frame(self._stopping)
                if not self._frames.full():
                    self._frames.put_nowait(('frame', pixels))
                delta = time.monotonic() - start
                if delta < 1 / 60:
                    time.sleep(1 / 60 - delta)
        except Exception as exc:
            try:
                self._frames.put_nowait(('error', str(exc)))
            except queue.Full:
                pass
        finally:
            try:
                self.machine.save()
            except OSError:
                pass

    def _pump(self):
        if self._closed:
            return
        try:
            latest = None
            for _ in range(4):
                try:
                    kind, data = self._frames.get_nowait()
                except queue.Empty:
                    break
                if kind == 'error':
                    self._paused.set()
                    self._status.set('Error del motor: ' + data[:80])
                    break
                latest = data
            if latest is not None:
                ppm = b'P6\n256 224\n255\n' + latest
                self._image = tk.PhotoImage(data=ppm, format='PPM')
                self._draw_frame()
                self._frame_displayed += 1
            now = time.monotonic()
            if now - self._last_fps_time >= 1:
                self._fps = self._frame_displayed / (now - self._last_fps_time)
                self._frame_displayed = 0
                self._last_fps_time = now
                if not self._paused.is_set():
                    self._status.set(f'Python nativo · {self._fps:.0f} FPS · sin audio')
        except tk.TclError:
            return
        self.after(30, self._pump)

    def _resize(self, _event=None):
        if self._image:
            self._draw_frame()

    def _draw_frame(self):
        if self._closed or not self._image:
            return
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        zoom = max(1, min(w // SCREEN_W, h // SCREEN_H, 4))
        self._shown_image = self._image.zoom(zoom, zoom) if zoom > 1 else self._image
        if self._photo_item is None:
            self._photo_item = self.canvas.create_image(w // 2, h // 2,
                                                         image=self._shown_image, anchor='center')
        else:
            self.canvas.coords(self._photo_item, w // 2, h // 2)
            self.canvas.itemconfigure(self._photo_item, image=self._shown_image)

    def _key_down(self, event):
        if event.keysym == 'F11':
            return
        self._pressed.add(event.keysym)
        self._update_keys()

    def _key_up(self, event):
        self._pressed.discard(event.keysym)
        self._update_keys()

    def _focus_out(self, _event=None):
        self._pressed.clear()
        self._update_keys()

    def _update_keys(self):
        mask = 0
        for key in self._pressed:
            bit = self.KEY_BITS.get(key)
            if bit is not None:
                mask |= 1 << bit
        self.machine.bus.controller = mask

    def _escape(self, _event=None):
        if self._fullscreen:
            self.toggle_fullscreen()

    def toggle_pause(self):
        if self._paused.is_set():
            self._paused.clear()
            self._status.set('Continuando emulación...')
        else:
            self._paused.set()
            self._status.set('Pausado')

    def toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        try:
            self.attributes('-fullscreen', self._fullscreen)
        except tk.TclError:
            self._fullscreen = False
        self.focus_set()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._stopping.set()
        try:
            self.destroy()
        except tk.TclError:
            pass
        if self._on_closed is not None:
            self._on_closed(self)


def _demo_rom():
    """ROM homebrew original, creada en memoria para comprobar CPU/PPU sin archivos."""
    rom = bytearray(32768)
    rom[0x7FC0:0x7FC0 + 21] = b'ARCHMOBA SNES DEMO   '
    rom[0x7FD5] = 0x20  # LoROM
    rom[0x7FDC:0x7FE0] = bytes((0xFF, 0xFF, 0, 0))
    rom[0x7FFC:0x7FFE] = bytes((0, 0x80))
    rom[0x7FFA:0x7FFC] = bytes((0, 0x81))
    rom[0x100] = 0x40  # RTI en NMI
    code = []

    def lda(value):
        code.extend((0xA9, value & 255))

    def sta(address):
        code.extend((0x8D, address & 255, (address >> 8) & 255))

    code.extend((0x78, 0xD8))  # SEI, CLD
    lda(0x80); sta(0x2100)  # pantalla en blanco mientras se inicializa
    lda(0); sta(0x2105)  # modo 0
    lda(1); sta(0x210B)  # tiles BG1 en 0x1000 bytes
    lda(0); sta(0x2107)  # tilemap BG1 en 0
    lda(1); sta(0x212C)  # habilitar BG1
    lda(0); sta(0x2121)  # inicio CGRAM
    for rgb555 in (0x1842, 0x7FC4, 0x585F, 0x7FFF):
        lda(rgb555 & 255); sta(0x2122)
        lda(rgb555 >> 8); sta(0x2122)
    lda(0); sta(0x2116)
    lda(8); sta(0x2117)  # VRAM palabra 0x0800 = byte 0x1000
    for row in range(8):
        lda(0xAA if row & 1 else 0x55); sta(0x2118)
        lda(0x55 if row & 1 else 0xAA); sta(0x2119)
    lda(0x0F); sta(0x2100)  # mostrar con brillo completo
    code.extend((0xCB, 0x80, 0xFD))  # WAI; BRA -3
    rom[:len(code)] = bytes(code)
    return bytes(rom)


class SnesEmulatorTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self.data_dir = _config_dir()
        self.state_file = self.data_dir / "state.json"
        self.roms = []
        self.recent = []
        self.favorites = []
        self.visible = {"all": [], "recent": [], "favorites": []}
        self.lists = {}
        self._selected_path = ""
        self._game_window = None
        self._running_rom = ""
        self._startup_demo_pending = True
        self._scan_queue = queue.Queue()
        self._scan_thread = None
        self._scan_cancel = threading.Event()
        self._render_job = None
        self._alive = True
        self.fullscreen_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Motor propio Python: agrega una ROM. Compatibilidad experimental.")
        self.title_var = tk.StringVar(value="Selecciona un juego")
        self.info_var = tk.StringVar(value="Archivos admitidos: SFC, SMC, FIG, SWC y ZIP")
        self.count_vars = {key: tk.StringVar(value="0 juegos")
                           for key in ("all", "recent", "favorites")}
        self._build_ui()
        self._load_state()
        self._refresh_lists()
        self.after(150, self._poll)
        # Opening the PTM tool immediately starts the original demo in a
        # floating window. Playing a ROM replaces that demo.
        self.after(450, self._open_startup_demo)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        style = ttk.Style(self)
        style.configure("SnesTitle.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("SnesMuted.TLabel", foreground="#687486")
        style.configure("Snes.TNotebook.Tab", padding=(14, 8))
        header = ttk.Frame(self, padding=(15, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="🎮 ARCHMOBA SNES", style="SnesTitle.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text="v" + TOOL_VERSION, style="SnesMuted.TLabel").grid(
            row=0, column=1, sticky="e")
        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 8))
        left = ttk.Frame(body, padding=5)
        right = ttk.Frame(body, padding=(12, 4))
        body.add(left, weight=2)
        body.add(right, weight=3)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        tools = ttk.Frame(left)
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(tools, text="+ ROM", command=self.add_roms).pack(side="left")
        ttk.Button(tools, text="+ Carpeta", command=self.add_folder).pack(
            side="left", padx=(5, 0))
        ttk.Button(tools, text="Detener", command=self.stop_scan).pack(
            side="left", padx=(5, 0))
        ttk.Button(tools, text="▶ Demo", command=self.play_demo).pack(
            side="left", padx=(5, 0))
        self.tabs = ttk.Notebook(left, style="Snes.TNotebook")
        self.tabs.grid(row=1, column=0, sticky="nsew")
        for key, title in (("all", "Todos"), ("recent", "Recientes"),
                           ("favorites", "Favoritos")):
            tab = ttk.Frame(self.tabs, padding=5)
            self.tabs.add(tab, text=title)
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(1, weight=1)
            ttk.Label(tab, textvariable=self.count_vars[key],
                      style="SnesMuted.TLabel").grid(row=0, column=0, sticky="w")
            holder = ttk.Frame(tab)
            holder.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
            holder.columnconfigure(0, weight=1)
            holder.rowconfigure(0, weight=1)
            box = tk.Listbox(holder, activestyle="none", exportselection=False,
                             font=("Segoe UI", 10), bd=0, highlightthickness=1)
            box.grid(row=0, column=0, sticky="nsew")
            scroll = ttk.Scrollbar(holder, orient="vertical", command=box.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            box.configure(yscrollcommand=scroll.set)
            box.bind("<<ListboxSelect>>", lambda event, k=key: self._on_select(k))
            box.bind("<Double-Button-1>", lambda event, k=key: self.play_selected(k))
            box.bind("<Return>", lambda event, k=key: self.play_selected(k))
            box.bind("<Button-3>", lambda event, k=key: self._context_menu(event, k))
            self.lists[key] = box
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self._on_select())
        search = ttk.Frame(left)
        search.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        search.columnconfigure(0, weight=1)
        ttk.Label(search, text="Buscar en todas las pestañas",
                  style="SnesMuted.TLabel").grid(row=0, column=0, columnspan=2,
                                                  sticky="w", pady=(0, 4))
        entry = ttk.Entry(search, textvariable=self.search_var)
        entry.grid(row=1, column=0, sticky="ew")
        entry.bind("<Escape>", lambda _event: self.search_var.set(""))
        ttk.Button(search, text="✕", width=3,
                   command=lambda: self.search_var.set("")).grid(
            row=1, column=1, padx=(5, 0))
        self.search_var.trace_add("write", lambda *_: self._schedule_render())

        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.preview = tk.Canvas(right, bg="#101827", bd=0, highlightthickness=0,
                                 height=220)
        self.preview.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.preview.bind("<Configure>", self._draw_console)
        ttk.Label(right, textvariable=self.title_var,
                  font=("Segoe UI", 13, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(right, textvariable=self.info_var,
                  style="SnesMuted.TLabel", wraplength=500).grid(
            row=2, column=0, sticky="w", pady=(2, 8))
        actions = ttk.Frame(right)
        actions.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(actions, text="▶ Jugar", command=self.play_selected).pack(side="left")
        ttk.Button(actions, text="★ Favorito", command=self.toggle_favorite).pack(
            side="left", padx=(5, 0))
        ttk.Button(actions, text="Abrir carpeta", command=self.open_folder).pack(
            side="left", padx=(5, 0))
        ttk.Button(actions, text="Quitar", command=self.remove_selected).pack(
            side="left", padx=(5, 0))
        config = ttk.LabelFrame(right, text="Motor ARCHMOBA integrado", padding=9)
        config.grid(row=4, column=0, sticky="ew")
        config.columnconfigure(0, weight=1)
        ttk.Label(config, text="CPU 65C816 + memoria + PPU en Python. No instala ni ejecuta Snes9x o RetroArch.",
                  wraplength=490).grid(row=0, column=0, sticky="w")
        ttk.Label(config, text="Compatibilidad inicial: LoROM/HiROM y fondos gráficos modos 0/1. "
                  "Sprites básicos; sin audio SPC700, prioridad exacta ni chips especiales.",
                  style="SnesMuted.TLabel", wraplength=490).grid(
            row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(config, text="Al iniciar, el juego aparece en una ventana flotante. "
                  "F11 permite cambiar a pantalla completa.",
                  style="SnesMuted.TLabel", wraplength=490).grid(
            row=2, column=0, sticky="w", pady=(7, 0))
        ttk.Label(config, text="Controles: flechas = mover; Z = B; X = A; A = Y; S = X; "
                  "Enter = Start; Shift = Select; Q/W = L/R; F11 = pantalla completa.",
                  style="SnesMuted.TLabel", wraplength=490).grid(
            row=3, column=0, sticky="w", pady=(5, 0))
        ttk.Button(right, text="Cerrar juego en ejecución",
                   command=self.close_game).grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Label(self, textvariable=self.status_var, style="SnesMuted.TLabel",
                  padding=(15, 2, 15, 10)).grid(row=2, column=0, sticky="ew")

    def _draw_console(self, event=None):
        c = self.preview
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        cx, cy = w / 2, h / 2
        scale = min(w / 410, h / 245, 1.5)
        def p(x, y):
            return cx + x * scale, cy + y * scale
        c.create_text(*p(0, -82), text="SUPER NINTENDO", fill="#B7C9E5",
                      font=("Segoe UI", max(10, int(16 * scale)), "bold"))
        x1, y1 = p(-165, -55)
        x2, y2 = p(165, 67)
        c.create_rectangle(x1, y1, x2, y2, fill="#D7D7DF", outline="#A7A8BA",
                           width=3)
        x1, y1 = p(-120, -35)
        x2, y2 = p(120, -12)
        c.create_rectangle(x1, y1, x2, y2, fill="#A9A9B7", outline="")
        for x, y, color in ((105, 20, "#7256B5"), (126, 35, "#B36E9E"),
                            (83, 35, "#5A9CBB"), (105, 49, "#6BAE88")):
            px, py = p(x, y)
            r = 10 * scale
            c.create_oval(px-r, py-r, px+r, py+r, fill=color, outline="#E9E9F1")
        c.create_text(*p(-70, 31), text="✚", fill="#404353",
                      font=("Segoe UI Symbol", max(12, int(34 * scale)), "bold"))
        c.create_text(*p(0, 35), text="START   SELECT", fill="#5A5C6B",
                      font=("Segoe UI", max(8, int(10 * scale)), "bold"))
        c.create_text(*p(0, 91), text="ARCHMOBA • SNES", fill="#7895C2",
                      font=("Segoe UI", max(9, int(12 * scale))))

    def _load_state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            for key, attr in (("roms", "roms"), ("recent", "recent"),
                              ("favorites", "favorites")):
                values = data.get(key, [])
                if isinstance(values, list):
                    setattr(self, attr, list(dict.fromkeys(
                        item for item in values if isinstance(item, str))))
            self.fullscreen_var.set(data.get("fullscreen") is True)
        except (OSError, ValueError, TypeError):
            pass

    def _save_state(self):
        data = {"roms": self.roms, "recent": self.recent,
                "favorites": self.favorites, "fullscreen": self.fullscreen_var.get()}
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            temp = self.state_file.with_suffix(".json.tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            os.replace(temp, self.state_file)
        except OSError:
            pass

    def _schedule_render(self):
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
        self._render_job = self.after(110, self._refresh_lists)

    def _refresh_lists(self):
        self._render_job = None
        query = self.search_var.get().strip().casefold()
        for key, paths in (("all", self.roms), ("recent", self.recent),
                           ("favorites", self.favorites)):
            filtered = [path for path in paths if query in path.casefold()]
            self.visible[key] = filtered
            widget = self.lists[key]
            widget.delete(0, "end")
            if filtered:
                widget.insert("end", *("★ " + Path(path).stem if path in self.favorites
                                       else Path(path).stem for path in filtered))
            else:
                widget.insert("end", "Sin coincidencias" if query else "Sin juegos")
            self.count_vars[key].set(f"{len(filtered)} de {len(paths)}" if query
                                     else f"{len(paths)} juegos")

    def _active_tab(self):
        idx = self.tabs.index(self.tabs.select())
        return ("all", "recent", "favorites")[idx]

    def _selected(self, key=None):
        key = key or self._active_tab()
        indices = self.lists[key].curselection()
        paths = self.visible[key]
        if indices and indices[0] < len(paths):
            return paths[indices[0]]
        return self._selected_path if self._selected_path in paths else ""

    def _on_select(self, key=None):
        path = self._selected(key)
        if not path:
            return
        self._selected_path = path
        name = Path(path).stem
        self.title_var.set(name)
        try:
            size = Path(path).stat().st_size / (1024 * 1024)
            self.info_var.set(f"{Path(path).suffix.upper()} • {size:.2f} MB\n{path}")
        except OSError:
            self.info_var.set("Archivo no disponible: " + path)

    def _add_paths(self, paths):
        known = set(self.roms)
        added = 0
        for item in paths:
            path = str(Path(item).expanduser().resolve())
            if Path(path).suffix.lower() in ROM_EXTS and path not in known:
                self.roms.append(path)
                known.add(path)
                added += 1
        if added:
            self.roms.sort(key=lambda path: (Path(path).name.casefold(), path.casefold()))
            self._save_state()
            self._schedule_render()
        return added

    def add_roms(self):
        paths = filedialog.askopenfilenames(
            parent=self, title="Seleccionar ROMs SNES",
            filetypes=[("Juegos SNES", "*.sfc *.smc *.fig *.swc *.zip"),
                       ("Todos", "*.*")])
        if paths:
            added = self._add_paths(paths)
            self.status_var.set(f"{added} juego(s) agregado(s) a la biblioteca.")

    def add_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Carpeta de ROMs SNES")
        if not folder:
            return
        if self._scan_thread and self._scan_thread.is_alive():
            messagebox.showinfo(TOOL_NAME, "Ya hay un escaneo en curso.", parent=self)
            return
        self._scan_cancel.clear()
        self.status_var.set("Buscando ROMs en " + folder)
        self._scan_thread = threading.Thread(target=self._scan_folder,
                                             args=(folder,), daemon=True)
        self._scan_thread.start()

    def _scan_folder(self, folder):
        batch, folders = [], 0
        try:
            for root, dirs, files in os.walk(folder, followlinks=False):
                if self._scan_cancel.is_set():
                    break
                dirs[:] = [name for name in dirs
                           if not os.path.islink(os.path.join(root, name))]
                folders += 1
                for name in files:
                    if self._scan_cancel.is_set():
                        break
                    if Path(name).suffix.lower() in ROM_EXTS:
                        batch.append(os.path.join(root, name))
                        if len(batch) >= 30:
                            self._scan_queue.put(("batch", batch))
                            batch = []
                if folders % 100 == 0:
                    self._scan_queue.put(("progress", folders))
            if batch:
                self._scan_queue.put(("batch", batch))
            self._scan_queue.put(("done", self._scan_cancel.is_set()))
        except Exception as exc:
            self._scan_queue.put(("error", str(exc)))

    def stop_scan(self):
        self._scan_cancel.set()

    def _poll(self):
        if not self._alive:
            return
        try:
            for _ in range(20):
                try:
                    message = self._scan_queue.get_nowait()
                except queue.Empty:
                    break
                kind = message[0]
                if kind == "batch":
                    self._add_paths(message[1])
                elif kind == "progress":
                    self.status_var.set(f"Buscando ROMs... {message[1]} carpetas")
                elif kind == "done":
                    self.status_var.set("Escaneo detenido" if message[1]
                                        else f"Escaneo completo: {len(self.roms)} juegos")
                elif kind == "error":
                    self.status_var.set("Error de escaneo: " + message[1])
        except tk.TclError:
            return
        try:
            if self.winfo_exists():
                self.after(180, self._poll)
        except tk.TclError:
            pass

    def _open_startup_demo(self):
        if not self._alive or not self._startup_demo_pending:
            return
        # Do not open windows for tools that PTM has instantiated but hidden.
        if not self.winfo_ismapped():
            return
        self._startup_demo_pending = False
        if self._game_window is None or not self._game_window.winfo_exists():
            self.play_demo()

    def play_demo(self):
        if self._game_window is not None and self._game_window.winfo_exists():
            self._game_window.lift()
            return
        try:
            self._game_window = NativeSnesWindow(
                self, 'Demo original ARCHMOBA SNES', _demo_rom(), None,
                fullscreen=False, on_closed=self._game_window_closed)
            self._running_rom = '__demo__'
            self._startup_demo_pending = False
            self.status_var.set('Demo original ejecutándose en ventana flotante. Usa Cerrar juego para salir.')
        except (OSError, ValueError, RuntimeError, tk.TclError) as exc:
            messagebox.showerror(TOOL_NAME, str(exc), parent=self)

    def play_selected(self, key=None):
        path = self._selected(key)
        if not path:
            messagebox.showinfo(TOOL_NAME, "Selecciona un juego de la biblioteca.", parent=self)
            return
        if self._game_window is not None and self._game_window.winfo_exists():
            if self._running_rom == '__demo__':
                self._game_window.close()
                self._game_window = None
            else:
                messagebox.showinfo(TOOL_NAME, "Cierra el juego actual antes de abrir otro.", parent=self)
                self._game_window.lift()
                return
        rom = Path(path)
        if not rom.is_file():
            messagebox.showerror(TOOL_NAME, "No se encontró la ROM:\n" + path, parent=self)
            return
        try:
            target = (_unpack_rom(rom, self.data_dir / "rom_cache")
                      if rom.suffix.lower() == ".zip" else rom)
            raw = target.read_bytes()
            save_name = hashlib.sha256(raw).hexdigest()[:24] + ".srm"
            save_path = self.data_dir / "saves" / save_name
            self._game_window = NativeSnesWindow(
                self, path, raw, save_path, fullscreen=False,
                on_closed=self._game_window_closed)
            self._running_rom = path
            self._startup_demo_pending = False
            self.recent = [path] + [item for item in self.recent if item != path]
            self.recent = self.recent[:50]
            self._save_state()
            self._schedule_render()
            self.status_var.set(f"Motor ARCHMOBA SNES propio ejecutando: {rom.stem}. Sin audio.")
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, tk.TclError) as exc:
            messagebox.showerror(TOOL_NAME, str(exc), parent=self)
            self.status_var.set("No se pudo iniciar: " + str(exc))

    def toggle_favorite(self):
        path = self._selected()
        if not path:
            return
        if path in self.favorites:
            self.favorites.remove(path)
        else:
            self.favorites.insert(0, path)
        self._save_state()
        self._schedule_render()

    def remove_selected(self):
        path = self._selected()
        if not path:
            return
        if path in self.roms:
            self.roms.remove(path)
        if path in self.recent:
            self.recent.remove(path)
        if path in self.favorites:
            self.favorites.remove(path)
        self._selected_path = ""
        self.title_var.set("Selecciona un juego")
        self.info_var.set("El archivo original no se elimina del disco.")
        self._save_state()
        self._schedule_render()

    def open_folder(self):
        path = self._selected()
        if not path:
            return
        folder = Path(path).parent
        if not folder.is_dir():
            return
        try:
            if os.name == "nt":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror(TOOL_NAME, str(exc), parent=self)

    def _context_menu(self, event, key):
        widget = self.lists[key]
        index = widget.nearest(event.y)
        if index >= len(self.visible[key]):
            return
        widget.selection_clear(0, "end")
        widget.selection_set(index)
        self._on_select(key)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="▶ Jugar", command=lambda: self.play_selected(key))
        menu.add_command(label="★ Añadir / quitar favorito", command=self.toggle_favorite)
        menu.add_command(label="Abrir carpeta", command=self.open_folder)
        menu.add_separator()
        menu.add_command(label="Quitar de biblioteca", command=self.remove_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _game_window_closed(self, window):
        if self._game_window is window:
            self._game_window = None
            self._running_rom = ''
            if self._alive:
                self.status_var.set('Ventana del juego cerrada. Selecciona una ROM para jugar.')

    def close_game(self):
        if self._game_window is None or not self._game_window.winfo_exists():
            self.status_var.set("No hay un juego en ejecución.")
            return
        self._game_window.close()
        self._game_window = None
        self.status_var.set("Juego cerrado. SRAM se guarda al detener el motor.")

    def on_show(self):
        self._schedule_render()
        if self._startup_demo_pending:
            self.after(250, self._open_startup_demo)

    def on_hide(self):
        # La ventana Tk de juego permanece abierta dentro del mismo proceso.
        pass

    def on_close(self):
        self._alive = False
        self._scan_cancel.set()
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
        self._save_state()
        if self._game_window is not None:
            self._game_window.close()


App = SnesEmulatorTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1080x690")
    root.minsize(780, 520)
    tool = App(root)
    tool.pack(fill="both", expand=True)
    def close():
        tool.on_close()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main()
