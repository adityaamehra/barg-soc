module bus_mux4 (
    input  wire        grant0,
    input  wire        grant1,
    input  wire        grant2,
    input  wire        grant3,
    input  wire [31:0] addr0,
    input  wire [31:0] addr1,
    input  wire [31:0] addr2,
    input  wire [31:0] addr3,
    input  wire [31:0] store_data0,
    input  wire [31:0] store_data1,
    input  wire [31:0] store_data2,
    input  wire [31:0] store_data3,
    input  wire [2:0]  memtype0,
    input  wire [2:0]  memtype1,
    input  wire [2:0]  memtype2,
    input  wire [2:0]  memtype3,
    input  wire [1:0]  memsrc0,
    input  wire [1:0]  memsrc1,
    input  wire [1:0]  memsrc2,
    input  wire [1:0]  memsrc3,
    input  wire        valid0,
    input  wire        valid1,
    input  wire        valid2,
    input  wire        valid3,
    input  wire        xcpt0,
    input  wire        xcpt1,
    input  wire        xcpt2,
    input  wire        xcpt3,
    input  wire        memwrite0,
    input  wire        memwrite1,
    input  wire        memwrite2,
    input  wire        memwrite3,
    input  wire        kill0,
    input  wire        kill1,
    input  wire        kill2,
    input  wire        kill3,
    input  wire        dmem_we0,
    input  wire        dmem_we1,
    input  wire        dmem_we2,
    input  wire        dmem_we3,
    input  wire [31:0] dmem_wdata0,
    input  wire [31:0] dmem_wdata1,
    input  wire [31:0] dmem_wdata2,
    input  wire [31:0] dmem_wdata3,
    output reg  [31:0] addr,
    output reg  [31:0] store_data,
    output reg  [2:0]  memtype,
    output reg  [1:0]  memsrc,
    output reg         valid,
    output reg         xcpt,
    output reg         memwrite,
    output reg         kill,
    output reg         dmem_we,
    output reg  [31:0] dmem_wdata
);

always @* begin
    // Default assignments
    addr         = 32'd0;
    store_data   = 32'd0;
    memtype      = 3'd0;
    memsrc       = 2'd0;
    valid        = 1'b0;
    xcpt         = 1'b0;
    memwrite     = 1'b0;
    kill         = 1'b0;
    dmem_we      = 1'b0;
    dmem_wdata   = 32'd0;

    if (grant0) begin
        addr         = addr0;
        store_data   = store_data0;
        memtype      = memtype0;
        memsrc       = memsrc0;
        valid        = valid0;
        xcpt         = xcpt0;
        memwrite     = memwrite0;
        kill         = kill0;
        dmem_we      = dmem_we0;
        dmem_wdata   = dmem_wdata0;
    end else if (grant1) begin
        addr         = addr1;
        store_data   = store_data1;
        memtype      = memtype1;
        memsrc       = memsrc1;
        valid        = valid1;
        xcpt         = xcpt1;
        memwrite     = memwrite1;
        kill         = kill1;
        dmem_we      = dmem_we1;
        dmem_wdata   = dmem_wdata1;
    end else if (grant2) begin
        addr         = addr2;
        store_data   = store_data2;
        memtype      = memtype2;
        memsrc       = memsrc2;
        valid        = valid2;
        xcpt         = xcpt2;
        memwrite     = memwrite2;
        kill         = kill2;
        dmem_we      = dmem_we2;
        dmem_wdata   = dmem_wdata2;
    end else if (grant3) begin
        addr         = addr3;
        store_data   = store_data3;
        memtype      = memtype3;
        memsrc       = memsrc3;
        valid        = valid3;
        xcpt         = xcpt3;
        memwrite     = memwrite3;
        kill         = kill3;
        dmem_we      = dmem_we3;
        dmem_wdata   = dmem_wdata3;
    end
end

endmodule
