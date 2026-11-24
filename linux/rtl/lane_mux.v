module lane_mux (
    input busy,
    input ptw_req,
    input [32:0] ptw_addr,
    input stall,
    input core_req,
    input [32:0] addr,
    input [32:0] store_data,
    input [3:0] memtype,
    input [2:0] memsrc,
    input valid,
    input xcpt,
    input memwrite,
    input kill,
    input dmem_we,
    input [32:0] dmem_wdata,
    output [32:0] addr_o,
    output [32:0] store_data_o,
    output [3:0] memtype_o,
    output [2:0] memsrc_o,
    output valid_o,
    output xcpt_o,
    output memwrite_o,
    output kill_o,
    output dmem_we_o,
    output [32:0] dmem_wdata_o,
    output req
);

    // Logic when busy is 1
    wire [32:0] addr_o_busy = ptw_addr;
    wire [32:0] store_data_o_busy = 32'b0;
    wire [3:0] memtype_o_busy = 4'b010;
    wire [2:0] memsrc_o_busy = 3'b01;
    wire valid_o_busy = 1'b1;
    wire xcpt_o_busy = 1'b0;
    wire memwrite_o_busy = 1'b0;
    wire kill_o_busy = 1'b0;
    wire dmem_we_o_busy = 1'b0;
    wire [32:0] dmem_wdata_o_busy = 32'b0;
    wire req_busy = ptw_req;

    // Logic when busy is 0
    wire [32:0] addr_o_idle = addr;
    wire [32:0] store_data_o_idle = store_data;
    wire [3:0] memtype_o_idle = memtype;
    wire [2:0] memsrc_o_idle = memsrc;
    wire valid_o_idle = valid;
    wire xcpt_o_idle = xcpt;
    wire memwrite_o_idle = memwrite;
    wire kill_o_idle = kill;
    wire dmem_we_o_idle = dmem_we;
    wire [32:0] dmem_wdata_o_idle = dmem_wdata;
    wire req_idle = core_req & ~stall;

    // Output assignments
    assign addr_o = busy ? addr_o_busy : addr_o_idle;
    assign store_data_o = busy ? store_data_o_busy : store_data_o_idle;
    assign memtype_o = busy ? memtype_o_busy : memtype_o_idle;
    assign memsrc_o = busy ? memsrc_o_busy : memsrc_o_idle;
    assign valid_o = busy ? valid_o_busy : valid_o_idle;
    assign xcpt_o = busy ? xcpt_o_busy : xcpt_o_idle;
    assign memwrite_o = busy ? memwrite_o_busy : memwrite_o_idle;
    assign kill_o = busy ? kill_o_busy : kill_o_idle;
    assign dmem_we_o = busy ? dmem_we_o_busy : dmem_we_o_idle;
    assign dmem_wdata_o = busy ? dmem_wdata_o_busy : dmem_wdata_o_idle;
    assign req = busy ? req_busy : req_idle;

endmodule
