"""Compile the portable firmware metrics module into a Windows host DLL and execute it.

Needs host-target Clang + LLD; --clang-dir can point at another installation.
The preinstalled MATLAB Clang is used by default, without starting MATLAB.
"""
import argparse
import ctypes
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--clang-dir",type=Path,default=Path(r"C:\Program Files\MATLAB\R2026a\toolbox\sldrt\clang\win64"))
    args=parser.parse_args()
    out=ROOT/"data"/"verification"/"native"
    out.mkdir(parents=True,exist_ok=True)
    for source,name in [(ROOT/"firmware/main/metrics.c","metrics"),(ROOT/"tests/firmware_metrics_host.c","test")]:
        subprocess.run([str(args.clang_dir/"clang.exe"),"-target","x86_64-pc-windows-msvc","-std=c11",
            "-ffreestanding","-fno-builtin","-O0","-Wall","-Wextra","-Werror",
            "-I",str(ROOT/"tests/host_include"),"-I",str(ROOT/"firmware/main"),
            "-c",str(source),"-o",str(out/f"{name}.obj")],check=True)
    subprocess.run([str(args.clang_dir/"lld.exe"),"-flavor","link","/dll","/noentry","/nodefaultlib",
                    "/machine:x64",f"/out:{out/'metrics-tests.dll'}",str(out/"metrics.obj"),str(out/"test.obj")],check=True)
    library=ctypes.CDLL(str(out/"metrics-tests.dll"))
    result=library.run_tests()
    if result:
        raise SystemExit(f"Firmware metric assertion failed at tests/firmware_metrics_host.c:{result}")
    print("Actual firmware metrics.c: duplicate/out-of-order/late packets, RTT timeout, jitter, drain, stop and recovery OK")


if __name__=="__main__":
    main()
