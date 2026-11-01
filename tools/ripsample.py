"""Sample the instruction pointer of every thread of a Windows process and map
it to symbols from `llvm-nm` of the executable (stdlib + ctypes only).

py -3 tools/ripsample.py PID EXE [--secs 2] [--hz 200] [--nm PATH]

For each thread: a histogram of where RIP was (exe symbol or system DLL) and a
heuristic call chain from scanning the stack for return addresses inside the
exe. Use it when a dev build stops making progress: a thread parked in
psx_fatal_halt means the runtime stopped on a fatal error (see runtime.log),
a thread spinning in exe code is a host-side loop. Windows x64 only.
"""
import argparse
import bisect
import collections
import ctypes
import ctypes.wintypes as wt
import subprocess
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
TH32CS_SNAPTHREAD = 0x4
TH32CS_SNAPMODULE = 0x8
THREAD_ALL = 0x0002 | 0x0008 | 0x0040  # SUSPEND_RESUME | GET_CONTEXT | QUERY_INFORMATION
CONTEXT_AMD64 = 0x00100000
CONTEXT_CONTROL = CONTEXT_AMD64 | 0x1
CONTEXT_INTEGER = CONTEXT_AMD64 | 0x2


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long), ("dwFlags", wt.DWORD)]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
                ("hModule", wt.HMODULE), ("szModule", ctypes.c_char * 256),
                ("szExePath", ctypes.c_char * 260)]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE


def threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def modules(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    me = MODULEENTRY32(); me.dwSize = ctypes.sizeof(me)
    out = []
    ok = k32.Module32First(snap, ctypes.byref(me))
    while ok:
        out.append((me.modBaseAddr, me.modBaseSize, me.szModule.decode(errors="replace")))
        ok = k32.Module32Next(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    return out


def get_rip_rsp(h):
    buf = (ctypes.c_byte * (1232 + 16))()
    addr = (ctypes.addressof(buf) + 15) & ~15
    ctypes.c_uint32.from_address(addr + 0x30).value = CONTEXT_CONTROL | CONTEXT_INTEGER  # ContextFlags
    if not k32.GetThreadContext(wt.HANDLE(h), ctypes.c_void_p(addr)):
        return None, None
    return ctypes.c_uint64.from_address(addr + 0xF8).value, ctypes.c_uint64.from_address(addr + 0x98).value


def load_symbols(exe, nm):
    out = subprocess.run([nm, "--defined-only", exe], capture_output=True, text=True).stdout
    syms = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in "tTwW":
            syms.append((int(parts[0], 16), parts[2]))
    syms.sort()
    return syms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int)
    ap.add_argument("exe")
    ap.add_argument("--secs", type=float, default=2.0)
    ap.add_argument("--hz", type=float, default=200)
    ap.add_argument("--nm", default=r"D:\RecompDev\Toolchain\bin\llvm-nm.exe")
    a = ap.parse_args()
    syms = load_symbols(a.exe, a.nm)
    addrs = [s[0] for s in syms]
    mods = modules(a.pid)
    base, size, _ = mods[0]
    pref = 0x140000000
    PROCESS_VM_READ = 0x0010 | 0x0400
    k32.OpenProcess.restype = wt.HANDLE
    hp = k32.OpenProcess(PROCESS_VM_READ, False, a.pid)
    stacks = {}

    def stack_scan(rsp, limit=0x4000):
        buf = (ctypes.c_ubyte * limit)()
        got = ctypes.c_size_t(0)
        k32.ReadProcessMemory(wt.HANDLE(hp), ctypes.c_void_p(rsp), buf, limit, ctypes.byref(got))
        frames = []
        for off in range(0, got.value - 7, 8):
            v = int.from_bytes(bytes(buf[off:off + 8]), "little")
            if base <= v < base + size:
                frames.append(name(v))
        return frames

    def where(rip):
        if base <= rip < base + size:
            return name(rip)
        for b, sz, nm_ in mods:
            if b <= rip < b + sz:
                return f"{nm_}+0x{rip - b:x}"
        return f"?{rip:x}"
    hist = collections.defaultdict(collections.Counter)
    t_end = time.monotonic() + a.secs
    handles = {tid: k32.OpenThread(THREAD_ALL, False, tid) for tid in threads(a.pid)}

    def name(rip):
        va = rip - base + pref
        i = bisect.bisect_right(addrs, va) - 1
        return syms[i][1] + "+0x%x" % (va - addrs[i]) if i >= 0 else "?%x" % rip

    while time.monotonic() < t_end:
        for tid, h in handles.items():
            if not h:
                continue
            if k32.SuspendThread(wt.HANDLE(h)) == 0xFFFFFFFF:
                continue
            rip, rsp = get_rip_rsp(h)
            st = stack_scan(rsp) if rip and tid not in stacks else None
            k32.ResumeThread(wt.HANDLE(h))
            if rip:
                n = where(rip)
                hist[tid][n.split("+")[0]] += 1
                if st is not None:
                    stacks[tid] = st
        time.sleep(1.0 / a.hz)
    for tid, c in hist.items():
        total = sum(c.values())
        top = c.most_common(6)
        print(f"thread {tid}: {total} samples")
        for fn, n in top:
            print(f"   {n:5d}  {fn}")
        print("   stack:", " <- ".join(dict.fromkeys(f.split("+")[0] for f in stacks.get(tid, [])[:40]).keys()))


if __name__ == "__main__":
    main()
