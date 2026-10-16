# CPS-1 68000 program region — World 930201

The parent set program contains three 512-KiB ROMs. The ordering is:

| ROM | Program offset | Bytes | Transform |
|---|---:|---:|---|
| cde_23a.8f | 0x000000 | 0x80000 | swap bytes within 16-bit words |
| cde_22a.7f | 0x080000 | 0x80000 | swap bytes within 16-bit words |
| cde_21a.6f | 0x100000 | 0x80000 | swap bytes within 16-bit words |

The 68000 is big-endian. Local reference-audit results:

- Program region: 1,572,864 bytes (0x180000).
- Reset stack pointer: `0x00FF0E66`.
- Reset program counter: `0x0000041A`.
- Reset PC is even and inside the assembled program region.

Run `python3 tools/cps1_program.py /path/to/dino.zip --json` locally to reproduce the metadata. It neither saves nor uploads ROM contents. These checks establish ROM region mapping only; they do **not** demonstrate executable game emulation or a Nintendo Switch build.

Run tests with `python3 -m unittest discover -s tests -v`.
