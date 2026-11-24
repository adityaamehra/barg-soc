module hart_memif (
    input  wire        core_req,
    input  wire        mmu_stall,
    input  wire        imiss,
    input  wire        ptw_req,
    input  wire        ifq,
    input  wire        grant,
    output wire        req,
    output wire [1:0]  kind,
    output wire        stall,
    output wire        run
);

    wire core_eff = core_req & ~mmu_stall & ~imiss;
    assign req   = core_eff | ptw_req | ifq;
    assign kind  = (ifq)      ? 2'b10 :
                   (ptw_req)  ? 2'b01 :
                                2'b00;
    assign stall = mmu_stall | imiss;
    assign run   = ~core_req | grant;

endmodule
