module uart16550f (
    input  wire         clk,
    input  wire         rst,
    input  wire [31:0]  addr,
    input  wire [31:0]  wdata,
    input  wire         we,
    input  wire         re,
    input  wire         rx_valid,
    input  wire [7:0]   rx_data,
    output wire [31:0]  rdata,
    output wire         irq,
    output wire         tx_valid,
    output wire [7:0]   tx_data
);

    // Held state
    reg [3:0]  IER;
    reg [7:0]  LCR;
    reg [4:0]  MCR;
    reg [7:0]  SCR;
    reg [7:0]  DLL;
    reg [7:0]  DLM;
    reg        FE;
    reg        TXF;
    reg        OE;
    reg [7:0]  fifo_mem [0:15];
    reg [3:0]  RP;
    reg [3:0]  WP;
    reg [4:0]  RXCNT;  // 0..16

    // Combinational outputs
    wire       rx_int_pending;
    wire       tx_int_pending;
    wire       interrupt_pending;
    wire [2:0] iir_bits_3_1;

    assign rx_int_pending   = IER[0] && (RXCNT != 0);
    assign tx_int_pending   = IER[1] && TXF;
    assign interrupt_pending = rx_int_pending || tx_int_pending;

    assign iir_bits_3_1 = rx_int_pending   ? 3'b010 :
                          tx_int_pending   ? 3'b001 :
                                             3'b000;

    // rdata
    assign rdata = (addr[2:0] == 3'd0) ? (LCR[7] ? {24'd0, DLL} : (RXCNT != 0 ? {24'd0, fifo_mem[RP]} : 32'd0)) :
                   (addr[2:0] == 3'd1) ? (LCR[7] ? {24'd0, DLM} : {28'd0, IER}) :
                   (addr[2:0] == 3'd2) ? {24'd0, {2{FE}}, 2'b00, iir_bits_3_1, ~interrupt_pending} :
                   (addr[2:0] == 3'd3) ? {24'd0, LCR} :
                   (addr[2:0] == 3'd4) ? {27'd0, MCR} :
                   (addr[2:0] == 3'd5) ? {24'd0, 1'b0, 1'b1, 1'b1, 3'b000, OE, (RXCNT != 0)} :
                   (addr[2:0] == 3'd6) ? 32'd0 :
                   (addr[2:0] == 3'd7) ? {24'd0, SCR} :
                                           32'd0;

    assign irq       = interrupt_pending;
    assign tx_valid  = we && (addr[2:0] == 3'd0) && !LCR[7];
    assign tx_data   = tx_valid ? wdata[7:0] : 8'd0;

    // Next-state signals
    reg [3:0]  IER_next;
    reg [7:0]  LCR_next;
    reg [4:0]  MCR_next;
    reg [7:0]  SCR_next;
    reg [7:0]  DLL_next;
    reg [7:0]  DLM_next;
    reg        FE_next;
    reg        TXF_next;
    reg        OE_next;
    reg [3:0]  RP_next;
    reg [3:0]  WP_next;
    reg [4:0]  RXCNT_next;
    reg        fifo_we;
    reg [3:0]  fifo_waddr;
    reg [7:0]  fifo_wdata;

    // Combinational next-state logic
    always @* begin
        // Default: hold
        IER_next    = IER;
        LCR_next    = LCR;
        MCR_next    = MCR;
        SCR_next    = SCR;
        DLL_next    = DLL;
        DLM_next    = DLM;
        FE_next     = FE;
        TXF_next    = TXF;
        OE_next     = OE;
        RP_next     = RP;
        WP_next     = WP;
        RXCNT_next  = RXCNT;
        fifo_we     = 1'b0;
        fifo_waddr  = 4'd0;
        fifo_wdata  = 8'd0;

        // Step 1: Reads
        if (re) begin
            case (addr[2:0])
                3'd0: if (!LCR[7] && RXCNT != 0) begin
                          RP_next    = RP + 1;
                          RXCNT_next = RXCNT - 1;
                      end
                3'd5: OE_next = 1'b0;
                3'd2: if (iir_bits_3_1 == 3'b001) TXF_next = 1'b0;
                default: ;
            endcase
        end

        // Step 2: Stores
        if (we) begin
            case (addr[2:0])
                3'd0: if (LCR[7]) DLL_next = wdata[7:0];
                      else        TXF_next = 1'b1;
                3'd1: if (LCR[7]) DLM_next = wdata[7:0];
                      else begin
                          IER_next = wdata[3:0];
                          if (IER[1] == 1'b0 && wdata[1] == 1'b1) TXF_next = 1'b1;
                      end
                3'd2: begin
                          FE_next = wdata[0];
                          if (wdata[1]) begin
                              RP_next    = 4'd0;
                              WP_next    = 4'd0;
                              RXCNT_next = 5'd0;
                          end
                      end
                3'd3: LCR_next = wdata[7:0];
                3'd4: MCR_next = wdata[4:0];
                3'd7: SCR_next = wdata[7:0];
                default: ;
            endcase
        end

        // Step 3: Receive
        if (rx_valid) begin
            if (RXCNT_next < 16) begin
                fifo_we     = 1'b1;
                fifo_waddr  = WP_next;
                fifo_wdata  = rx_data;
                WP_next     = WP_next + 1;
                RXCNT_next  = RXCNT_next + 1;
            end else begin
                OE_next = 1'b1;
            end
        end
    end

    // Sequential state update
    integer i;
    always @(posedge clk) begin
        if (rst) begin
            IER    <= 4'd0;
            LCR    <= 8'd0;
            MCR    <= 5'd0;
            SCR    <= 8'd0;
            DLL    <= 8'd0;
            DLM    <= 8'd0;
            FE     <= 1'b0;
            TXF    <= 1'b0;
            OE     <= 1'b0;
            RP     <= 4'd0;
            WP     <= 4'd0;
            RXCNT  <= 5'd0;
            for (i = 0; i < 16; i = i + 1) fifo_mem[i] <= 8'd0;
        end else begin
            IER    <= IER_next;
            LCR    <= LCR_next;
            MCR    <= MCR_next;
            SCR    <= SCR_next;
            DLL    <= DLL_next;
            DLM    <= DLM_next;
            FE     <= FE_next;
            TXF    <= TXF_next;
            OE     <= OE_next;
            RP     <= RP_next;
            WP     <= WP_next;
            RXCNT  <= RXCNT_next;
            if (fifo_we) fifo_mem[fifo_waddr] <= fifo_wdata;
        end
    end

endmodule
