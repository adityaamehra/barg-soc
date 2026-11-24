# Renders

| Folder | What | Where it came from |
|---|---|---|
| [`fpga/`](fpga/) | `gouraud-320x240.png` and a 3x enlargement | the GPU running on the ZCU104 FPGA; frame read back from video memory, sent over the UART with gzip. Identical to the frame model in all 76,800 pixels. |
| [`cluster-sim/`](cluster-sim/) | ten scenes (`core<N>_<scene>_<seed>.png`) and `contact_sheet.png` | ten GPU cores on the SoC's generated Verilog in Verilator (2,868,953 cycles); every pixel checked against the frame model. |
