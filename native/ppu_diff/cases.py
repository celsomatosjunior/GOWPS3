# SPDX-License-Identifier: GPL-2.0-only
"""Casos do teste diferencial: (função, assinatura, entradas).

Assinaturas: i=int32, l=int64, u=uint32, d=double, f=float. "ii>i" = int f(int,int).
Fonte única para o main PowerPC (QEMU), o main nativo e o driver do código recompilado.
"""

CASES = [
    ("arith", "ii>i", [(5, 3), (-7, 2), (100, -100), (0, 0), (123456, -98765), (-2147483648, 5)]),
    ("branches", "ii>i", [(1, 2), (2, 1), (3, 3), (-1, 1), (-1, -2), (0, -1)]),
    ("rotates", "ii>i", [(0x12345678, 5), (-1, 13), (-2147483647, 1), (7, 0), (-559038737, 20)]),
    ("mul64", "ll>l", [(3, 5), (-7, 11), (0x100000001, 0x30), (-1, -1), (0x7FFFFFFFFFFFFFFF, 2)]),
    ("mulhigh", "ll>l", [(3, 5), (-7, 11), (0x123456789ABCDEF, 0x7EDCBA987654321), (-1, -1),
                         (-0x7FFFFFFFFFFFFFFF, 0x7FFFFFFFFFFFFFFF)]),
    ("divmod", "ll>l", [(100, 7), (-100, 7), (100, -7), (0x7FFFFFFFFFFFFFFF, 3), (5, 0), (-9, -2)]),
    ("clz_bswap", "i>i", [(1,), (0x40000000,), (0xFFFF,), (0x00010000,), (0x7FFFFFFF,), (-1,)]),
    ("stack_loop", "i>i", [(0,), (1,), (7,), (31,), (-5,), (1000,)]),
    ("fib", "i>i", [(0,), (1,), (2,), (10,), (20,)]),
    ("calls", "ii>i", [(3, 4), (-5, 9), (100, 200), (0, 0)]),
    ("jump_table", "ii>i", [(op, v) for op in range(-1, 12) for v in (77,)] + [(9, -1000), (4, -3)]),
    ("table_lookup", "ii>i", [(0, 0), (3, 9), (15, 1), (-1, 7), (12345, 678)]),
    ("hash_text", "i>u", [(0,), (1,), (-1,), (0x1234,)]),
    ("global_rw", "ii>i", [(0, 5), (1, 3), (2, -4), (3, 10), (0, 1), (6, 2)]),
    ("poly", "dd>d", [(1.5, 2.0), (-3.25, 0.5), (100.0, 7.0), (0.1, -0.1), (1e10, 3.0)]),
    ("fmix", "ff>f", [(1.5, 2.0), (-3.25, 0.5), (10.0, 4.0), (0.3, 0.7)]),
    ("conv", "di>i", [(1.75, 3), (-2.5, -8), (12345.678, 100), (0.0, 0)]),
]

CTYPE = {"i": "int", "l": "int64_t", "u": "unsigned", "d": "double", "f": "float"}


def literal(kind, value):
    if kind == "l":
        return f"(int64_t){value}LL" if value >= 0 else f"(int64_t)({value}LL)"
    if kind == "i":
        return f"(int)({value})" if value >= -2147483647 else "(int)(-2147483647-1)"
    if kind == "d":
        return repr(float(value))
    if kind == "f":
        return repr(float(value)) + "f"
    return str(value)


def parse(sig):
    args, ret = sig.split(">")
    return list(args), ret
