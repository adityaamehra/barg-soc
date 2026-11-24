module bus_ctl_i (
    input  wire        memwrite,
    input  wire [1:0]  memsrc,
    input  wire        valid,
    input  wire        xcpt,
    input  wire        kill,
    input  wire        sel_ram,
    input  wire        sel_clint,
    input  wire        sel_plic,
    input  wire        sel_uart,
    input  wire        sel_periph,
    input  wire        sel_gpu,
    input  wire        idle,
    output wire        ram_we,
    output wire        clint_we,
    output wire        plic_we,
    output wire        uart_we,
    output wire        periph_we,
    output wire        gpu_we,
    output wire        plic_re,
    output wire        uart_re,
    output wire        periph_re,
    output wire        gpu_re
);

    wire read_enable = (memsrc == 2'b01) && valid && !xcpt && !kill;

    assign ram_we     = memwrite && sel_ram;
    assign clint_we   = memwrite && sel_clint && idle;
    assign plic_we    = memwrite && sel_plic && idle;
    assign uart_we    = memwrite && sel_uart && idle;
    assign periph_we  = memwrite && sel_periph && idle;
    assign gpu_we     = memwrite && sel_gpu && idle;

    assign plic_re    = read_enable && sel_plic && idle;
    assign uart_re    = read_enable && sel_uart && idle;
    assign periph_re  = read_enable && sel_periph && idle;
    assign gpu_re     = read_enable && sel_gpu && idle;

endmodule
