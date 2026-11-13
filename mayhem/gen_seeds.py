#!/usr/bin/env python3
"""Writes the small hand-assembled bitstreams used as fuzz seeds and as oracle input.

usage: gen_seeds.py <outdir>   (creates <outdir>/<codec>/<name>.bin)
"""
import os
import sys


class Bits:
    def __init__(self):
        self.bits = []

    def u(self, n, v):
        for i in range(n - 1, -1, -1):
            self.bits.append((v >> i) & 1)

    def ue(self, v):
        v += 1
        n = v.bit_length()
        self.u(n - 1, 0)
        self.u(n, v)

    def se(self, v):
        self.ue(2 * v - 1 if v > 0 else -2 * v)

    def align0(self):
        while len(self.bits) % 8:
            self.bits.append(0)

    def trailing(self):
        self.bits.append(1)
        self.align0()

    def raw(self, bs):
        assert len(self.bits) % 8 == 0
        for b in bs:
            self.u(8, b)

    def bytes(self):
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            chunk = self.bits[i:i + 8]
            chunk = chunk + [0] * (8 - len(chunk))
            v = 0
            for b in chunk:
                v = (v << 1) | b
            out.append(v)
        return bytes(out)


def noise(n, seed):
    out = bytearray()
    x = seed
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((x >> 16) & 0xFF)
    return bytes(out)


def epb(rbsp):
    out = bytearray()
    zeros = 0
    for b in rbsp:
        if zeros >= 2 and b <= 3:
            out.append(3)
            zeros = 0
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


SC = b"\x00\x00\x00\x01"

# ---------------------------------------------------------------- H.264

def h264_nal(ref_idc, typ, rbsp):
    return SC + bytes([(ref_idc << 5) | typ]) + epb(rbsp)


def h264_sps(w_mbs, h_mbs):
    b = Bits()
    b.u(8, 66)
    b.u(8, 0xC0)
    b.u(8, 30)
    b.ue(0)
    b.ue(0)
    b.ue(0)
    b.ue(0)
    b.ue(1)
    b.u(1, 0)
    b.ue(w_mbs - 1)
    b.ue(h_mbs - 1)
    b.u(1, 1)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.trailing()
    return h264_nal(3, 7, b.bytes())


def h264_pps():
    b = Bits()
    b.ue(0)
    b.ue(0)
    b.u(1, 0)
    b.u(1, 0)
    b.ue(0)
    b.ue(0)
    b.ue(0)
    b.u(1, 0)
    b.u(2, 0)
    b.se(0)
    b.se(0)
    b.se(0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.trailing()
    return h264_nal(3, 8, b.bytes())


def h264_idr_pcm(w_mbs, h_mbs, luma, idr_id):
    b = Bits()
    b.ue(0)
    b.ue(7)
    b.ue(0)
    b.u(4, 0)
    b.ue(idr_id)
    b.u(4, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.se(0)
    for _ in range(w_mbs * h_mbs):
        b.ue(25)
        b.align0()
        b.raw(bytes([luma]) * 256 + bytes([128]) * 128)
    b.trailing()
    return h264_nal(3, 5, b.bytes())


def h264_stream(w_mbs, h_mbs, luma, frames=1):
    return h264_sps(w_mbs, h_mbs) + h264_pps() + b"".join(
        h264_idr_pcm(w_mbs, h_mbs, luma + 7 * i, i) for i in range(frames))

# ---------------------------------------------------------------- H.265

def h265_nal(typ, rbsp):
    return SC + bytes([typ << 1, 1]) + epb(rbsp)


def h265_ptl(b):
    b.u(2, 0)
    b.u(1, 0)
    b.u(5, 1)
    b.u(32, 0x60000000)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(43, 0)
    b.u(1, 0)
    b.u(8, 93)


def h265_vps():
    b = Bits()
    b.u(4, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(6, 0)
    b.u(3, 0)
    b.u(1, 1)
    b.u(16, 0xFFFF)
    h265_ptl(b)
    b.u(1, 1)
    b.ue(1)
    b.ue(0)
    b.ue(0)
    b.u(6, 0)
    b.ue(0)
    b.u(1, 0)
    b.u(1, 0)
    b.trailing()
    return h265_nal(32, b.bytes())


def h265_sps(w, h):
    b = Bits()
    b.u(4, 0)
    b.u(3, 0)
    b.u(1, 1)
    h265_ptl(b)
    b.ue(0)
    b.ue(1)
    b.ue(w)
    b.ue(h)
    b.u(1, 0)
    b.ue(0)
    b.ue(0)
    b.ue(4)
    b.u(1, 1)
    b.ue(1)
    b.ue(0)
    b.ue(0)
    b.ue(0)
    b.ue(1)
    b.ue(0)
    b.ue(1)
    b.ue(0)
    b.ue(0)
    for _ in range(4):
        b.u(1, 0)
    b.ue(0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.trailing()
    return h265_nal(33, b.bytes())


def h265_pps():
    b = Bits()
    b.ue(0)
    b.ue(0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(3, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.ue(0)
    b.ue(0)
    b.se(0)
    for _ in range(3):
        b.u(1, 0)
    b.se(0)
    b.se(0)
    for _ in range(9):
        b.u(1, 0)
    b.ue(0)
    b.u(1, 0)
    b.u(1, 0)
    b.trailing()
    return h265_nal(34, b.bytes())


def h265_idr(seed):
    b = Bits()
    b.u(1, 1)
    b.u(1, 0)
    b.ue(0)
    b.ue(2)
    b.se(0)
    b.trailing()
    b.raw(noise(60, seed))
    return h265_nal(19, b.bytes())

# ---------------------------------------------------------------- JPEG

DC_BITS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
DC_VALS = list(range(12))
AC_BITS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D]
AC_VALS = [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
    0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
    0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
    0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA]


def huff_codes(bits, vals):
    codes = {}
    code = 0
    k = 0
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            codes[vals[k]] = (code, length)
            code += 1
            k += 1
        code <<= 1
    return codes


def jpeg_marker(m, payload):
    return bytes([0xFF, m]) + (len(payload) + 2).to_bytes(2, "big") + payload


def jpeg(w, h, sampling=0x22):
    dc = huff_codes(DC_BITS, DC_VALS)
    ac = huff_codes(AC_BITS, AC_VALS)
    hmax = sampling >> 4
    vmax = sampling & 15
    comps = [(1, sampling), (2, 0x11), (3, 0x11)]
    mcu_w = 8 * hmax
    mcu_h = 8 * vmax
    mcus = ((w + mcu_w - 1) // mcu_w) * ((h + mcu_h - 1) // mcu_h)
    b = Bits()
    pred = {1: 0, 2: 0, 3: 0}
    dcval = {1: 40, 2: 5, 3: -5}
    for _ in range(mcus):
        for cid, samp in comps:
            for _blk in range((samp >> 4) * (samp & 15)):
                diff = dcval[cid] - pred[cid]
                pred[cid] = dcval[cid]
                cat = abs(diff).bit_length()
                code, ln = dc[cat]
                b.u(ln, code)
                if cat:
                    b.u(cat, diff if diff > 0 else diff + (1 << cat) - 1)
                code, ln = ac[0x00]
                b.u(ln, code)
    while len(b.bits) % 8:
        b.bits.append(1)
    scan = b.bytes().replace(b"\xff", b"\xff\x00")
    out = b"\xff\xd8"
    out += jpeg_marker(0xDB, bytes([0]) + bytes([16] * 64))
    sof = bytes([8]) + h.to_bytes(2, "big") + w.to_bytes(2, "big") + bytes([3])
    for cid, samp in comps:
        sof += bytes([cid, samp, 0])
    out += jpeg_marker(0xC0, sof)
    out += jpeg_marker(0xC4, bytes([0x00]) + bytes(DC_BITS) + bytes(DC_VALS))
    out += jpeg_marker(0xC4, bytes([0x10]) + bytes(AC_BITS) + bytes(AC_VALS))
    sos = bytes([3]) + bytes([1, 0x00, 2, 0x00, 3, 0x00]) + bytes([0, 63, 0])
    out += jpeg_marker(0xDA, sos)
    out += scan + b"\xff\xd9"
    return out

# ---------------------------------------------------------------- MPEG-2

def mpeg2(w, h):
    b = Bits()
    b.raw(b"\x00\x00\x01\xb3")
    b.u(12, w)
    b.u(12, h)
    b.u(4, 1)
    b.u(4, 3)
    b.u(18, 0x3FFFF)
    b.u(1, 1)
    b.u(10, 112)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.raw(b"\x00\x00\x01\xb5")
    b.u(4, 1)
    b.u(8, 0x48)
    b.u(1, 1)
    b.u(2, 1)
    b.u(2, 0)
    b.u(2, 0)
    b.u(12, 0)
    b.u(1, 1)
    b.u(8, 0)
    b.u(1, 0)
    b.u(2, 0)
    b.u(5, 0)
    b.align0()
    b.raw(b"\x00\x00\x01\xb8")
    b.u(25, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(5, 0)
    b.align0()
    b.raw(b"\x00\x00\x01\x00")
    b.u(10, 0)
    b.u(3, 1)
    b.u(16, 0xFFFF)
    b.u(1, 0)
    b.align0()
    b.raw(b"\x00\x00\x01\xb5")
    b.u(4, 8)
    for _ in range(4):
        b.u(4, 15)
    b.u(2, 0)
    b.u(2, 3)
    b.u(1, 1)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(1, 0)
    b.align0()
    b.raw(b"\x00\x00\x01\x01")
    b.raw(noise(40, 7).replace(b"\x00", b"\x55"))
    b.raw(b"\x00\x00\x01\xb7")
    return b.bytes()

# ---------------------------------------------------------------- VP8 / VP9 / AV1

def vp8(w, h, size=32):
    tag = (0) | (0 << 1) | (1 << 4) | (size << 5)
    out = tag.to_bytes(3, "little") + b"\x9d\x01\x2a" + w.to_bytes(2, "little") + h.to_bytes(2, "little")
    return out + noise(size + 20, 11)


def vp9(w, h):
    b = Bits()
    b.u(2, 2)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(1, 0)
    b.u(24, 0x498342)
    b.u(3, 2)
    b.u(1, 0)
    b.u(16, w - 1)
    b.u(16, h - 1)
    b.u(1, 0)
    b.u(1, 1)
    b.u(1, 0)
    b.u(2, 0)
    b.u(6, 10)
    b.u(3, 0)
    b.u(1, 0)
    b.u(8, 60)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(16, 12)
    b.align0()
    return b.bytes() + noise(60, 13)


def leb128(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def av1_obu(typ, payload):
    return bytes([(typ << 3) | 2]) + leb128(len(payload)) + payload


def av1(w, h):
    b = Bits()
    b.u(3, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(5, 0)
    b.u(12, 0)
    b.u(5, 8)
    b.u(1, 0)
    b.u(4, 15)
    b.u(4, 15)
    b.u(16, w - 1)
    b.u(16, h - 1)
    b.u(1, 0)
    for _ in range(7):
        b.u(1, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(2, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.trailing()
    return av1_obu(2, b"") + av1_obu(1, b.bytes()) + av1_obu(6, noise(40, 17))

# ---------------------------------------------------------------- MPEG-4 / H.263

def mpeg4(w, h):
    b = Bits()
    b.raw(b"\x00\x00\x01\xb0\x01")
    b.raw(b"\x00\x00\x01\xb5\x09")
    b.raw(b"\x00\x00\x01\x00")
    b.raw(b"\x00\x00\x01\x20")
    b.u(1, 0)
    b.u(8, 1)
    b.u(1, 0)
    b.u(4, 1)
    b.u(1, 0)
    b.u(2, 0)
    b.u(1, 1)
    b.u(16, 30)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 1)
    b.u(13, w)
    b.u(1, 1)
    b.u(13, h)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.align0()
    b.raw(b"\x00\x00\x01\xb6")
    b.u(2, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(5, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(3, 0)
    b.u(5, 8)
    b.align0()
    b.raw(noise(48, 19))
    return b.bytes()


def h263(fmt):
    b = Bits()
    b.u(22, 0x20)
    b.u(8, 0)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(3, fmt)
    b.u(1, 0)
    b.u(4, 0)
    b.u(5, 10)
    b.u(1, 0)
    b.u(1, 0)
    b.align0()
    return b.bytes() + noise(64, 23)

# ---------------------------------------------------------------- AVS / AVS2

def avs(w, h):
    b = Bits()
    b.raw(b"\x00\x00\x01\xb0")
    b.u(8, 0x20)
    b.u(8, 0x42)
    b.u(1, 1)
    b.u(14, w)
    b.u(14, h)
    b.u(2, 1)
    b.u(3, 1)
    b.u(4, 1)
    b.u(4, 3)
    b.u(18, 100)
    b.u(1, 1)
    b.u(12, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(18, 1000)
    b.u(3, 0)
    b.align0()
    b.raw(b"\x00\x00\x01\xb3")
    b.u(16, 0xFFFF)
    b.u(1, 0)
    b.u(1, 1)
    b.u(8, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 1)
    b.u(6, 20)
    b.align0()
    b.raw(b"\x00\x00\x01\x00")
    b.raw(noise(40, 29).replace(b"\x00", b"\x41"))
    return b.bytes()


def avs2(w, h):
    b = Bits()
    b.raw(b"\x00\x00\x01\xb0")
    b.u(8, 0x20)
    b.u(8, 0x42)
    b.u(1, 1)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 0)
    b.u(1, 1)
    b.u(14, w)
    b.u(1, 1)
    b.u(14, h)
    b.u(2, 1)
    b.u(3, 1)
    b.u(4, 1)
    b.u(4, 3)
    b.u(18, 100)
    b.u(1, 1)
    b.u(12, 0)
    b.u(1, 1)
    b.u(1, 1)
    b.u(18, 1000)
    b.u(1, 0)
    b.u(3, 0)
    b.align0()
    b.raw(b"\x00\x00\x01\xb3")
    b.raw(noise(40, 31).replace(b"\x00", b"\x41"))
    return b.bytes()


def main(outdir):
    seeds = {
        "h264": {
            "idr_64x48": h264_stream(4, 3, 90),
            "idr3_80x64": h264_stream(5, 4, 60, frames=3),
            "idr_128x96": h264_stream(8, 6, 120),
            "headers_only": h264_sps(6, 4) + h264_pps(),
        },
        "h265": {
            "idr_64x64": h265_vps() + h265_sps(64, 64) + h265_pps() + h265_idr(3),
            "idr_128x64": h265_vps() + h265_sps(128, 64) + h265_pps() + h265_idr(5),
            "headers_only": h265_vps() + h265_sps(96, 96) + h265_pps(),
        },
        "jpeg": {
            "yuv420_40x24": jpeg(40, 24, 0x22),
            "yuv422_32x16": jpeg(32, 16, 0x21),
            "yuv444_16x16": jpeg(16, 16, 0x11),
        },
        "mpeg2": {"seq_pic_64x48": mpeg2(64, 48), "seq_pic_176x144": mpeg2(176, 144)},
        "vp8": {"key_64x48": vp8(64, 48), "key_176x144": vp8(176, 144)},
        "vp9": {"key_64x64": vp9(64, 64), "key_128x96": vp9(128, 96)},
        "av1": {"seq_64x64": av1(64, 64), "seq_176x144": av1(176, 144)},
        "mpeg4": {"vol_vop_64x48": mpeg4(64, 48), "vol_vop_176x144": mpeg4(176, 144)},
        "h263": {"psc_qcif": h263(2), "psc_cif": h263(3)},
        "avs": {"seq_pic_64x48": avs(64, 48), "seq_pic_176x144": avs(176, 144)},
        "avs2": {"seq_64x48": avs2(64, 48), "seq_176x144": avs2(176, 144)},
    }
    for codec, files in seeds.items():
        d = os.path.join(outdir, codec)
        os.makedirs(d, exist_ok=True)
        for name, data in files.items():
            with open(os.path.join(d, name + ".bin"), "wb") as f:
                f.write(data)


if __name__ == "__main__":
    main(sys.argv[1])
