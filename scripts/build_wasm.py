#!/usr/bin/env python3
"""Hand-assemble app/static/wasm/mandel.wasm — no toolchain needed.

Exports  mandel(width, height, max_iter)  which writes one byte per pixel
(iteration count scaled to 0..255) into linear memory, row-major. The Web Lab
runs the identical algorithm in JavaScript and times both.

    python scripts/build_wasm.py        # writes the .wasm and prints its size
"""
import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'app' / 'static' / 'wasm' / 'mandel.wasm'


def uleb(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def sleb(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        done = (n == 0 and not byte & 0x40) or (n == -1 and byte & 0x40)
        out.append(byte if done else byte | 0x80)
        if done:
            return bytes(out)


def section(sid: int, payload: bytes) -> bytes:
    return bytes([sid]) + uleb(len(payload)) + payload


def vec(items: list[bytes]) -> bytes:
    return uleb(len(items)) + b''.join(items)


def name(text: str) -> bytes:
    data = text.encode()
    return uleb(len(data)) + data


# --- opcodes ---------------------------------------------------------------
BLOCK, LOOP, END, BR, BR_IF = b'\x02\x40', b'\x03\x40', b'\x0b', b'\x0c', b'\x0d'
LGET, LSET, LTEE = 0x20, 0x21, 0x22
I32C, F64C = 0x41, 0x44
I32_ADD, I32_MUL, I32_DIV_S, I32_GE_S, I32_GT_S = b'\x6a', b'\x6c', b'\x6d', b'\x4e', b'\x4a'
F64_ADD, F64_SUB, F64_MUL, F64_DIV, F64_GT = b'\xa0', b'\xa1', b'\xa2', b'\xa3', b'\x64'
F64_CONVERT_I32_S = b'\xb7'
I32_STORE8 = b'\x3a\x00\x00'          # align=0 offset=0
SELECT = b'\x1b'


def lget(i): return bytes([LGET]) + uleb(i)
def lset(i): return bytes([LSET]) + uleb(i)
def ltee(i): return bytes([LTEE]) + uleb(i)
def i32(v): return bytes([I32C]) + sleb(v)
def f64(v): return bytes([F64C]) + struct.pack('<d', v)


# --- locals: params 0..2 = width, height, max_iter --------------------------
X, Y, I = 3, 4, 5                       # i32
CR, CI, ZR, ZI, TMP = 6, 7, 8, 9, 10    # f64

body = b''.join([
    # y = 0
    i32(0), lset(Y),
    BLOCK, LOOP,                                    # outer: rows
        lget(Y), lget(1), I32_GE_S, BR_IF, uleb(1),        # if y >= height: exit outer
        # x = 0
        i32(0), lset(X),
        BLOCK, LOOP,                                # inner: columns
            lget(X), lget(0), I32_GE_S, BR_IF, uleb(1),    # if x >= width: exit inner
            # cr = x / width * 3.5 - 2.5
            lget(X), F64_CONVERT_I32_S, lget(0), F64_CONVERT_I32_S, F64_DIV, f64(3.5), F64_MUL, f64(2.5), F64_SUB, lset(CR),
            # ci = y / height * 2.0 - 1.0
            lget(Y), F64_CONVERT_I32_S, lget(1), F64_CONVERT_I32_S, F64_DIV, f64(2.0), F64_MUL, f64(1.0), F64_SUB, lset(CI),
            # zr = zi = 0; i = 0
            f64(0.0), lset(ZR), f64(0.0), lset(ZI), i32(0), lset(I),
            BLOCK, LOOP,                            # iterate
                lget(I), lget(2), I32_GE_S, BR_IF, uleb(1),          # i >= max_iter: exit
                # zr*zr + zi*zi > 4.0 : exit
                lget(ZR), lget(ZR), F64_MUL, lget(ZI), lget(ZI), F64_MUL, F64_ADD, f64(4.0), F64_GT, BR_IF, uleb(1),
                # tmp = zr*zr - zi*zi + cr
                lget(ZR), lget(ZR), F64_MUL, lget(ZI), lget(ZI), F64_MUL, F64_SUB, lget(CR), F64_ADD, lset(TMP),
                # zi = 2*zr*zi + ci
                f64(2.0), lget(ZR), F64_MUL, lget(ZI), F64_MUL, lget(CI), F64_ADD, lset(ZI),
                # zr = tmp ; i++
                lget(TMP), lset(ZR),
                lget(I), i32(1), I32_ADD, lset(I),
                BR, uleb(0),
            END, END,
            # mem[y*width + x] = i * 255 / max_iter
            lget(Y), lget(0), I32_MUL, lget(X), I32_ADD,            # address
            lget(I), i32(255), I32_MUL, lget(2), I32_DIV_S,          # value
            I32_STORE8,
            # x++
            lget(X), i32(1), I32_ADD, lset(X),
            BR, uleb(0),
        END, END,
        # y++
        lget(Y), i32(1), I32_ADD, lset(Y),
        BR, uleb(0),
    END, END,
    END,                                            # function end
])

locals_decl = vec([uleb(3) + b'\x7f', uleb(5) + b'\x7c'])   # 3 × i32, 5 × f64
func_body = uleb(len(locals_decl) + len(body)) + locals_decl + body

module = b''.join([
    b'\x00asm', struct.pack('<I', 1),
    section(1, vec([b'\x60' + vec([b'\x7f', b'\x7f', b'\x7f']) + vec([])])),   # type: (i32,i32,i32)->()
    section(3, vec([uleb(0)])),                                                   # one function of type 0
    section(5, vec([b'\x00' + uleb(32)])),                                        # memory: min 32 pages (2 MB)
    section(7, vec([name('mandel') + b'\x00' + uleb(0), name('memory') + b'\x02' + uleb(0)])),
    section(10, vec([func_body])),
])

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_bytes(module)
print(f'wrote {OUT} ({len(module)} bytes)')
