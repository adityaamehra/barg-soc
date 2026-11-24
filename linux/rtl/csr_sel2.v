module csr_sel2 (
    input  wire [31:0] inst,
    input  wire [2:0]  csrop,
    input  wire [1:0]  priv,
    input  wire        tvm,
    input  wire [2:0]  mcounteren,
    input  wire [2:0]  scounteren,
    output reg  [5:0]  sel,
    output reg         illegal
);

    reg        is_access, is_write, bad;
    reg [1:0]  b;

    always @* begin
        // Default assignments to avoid latches
        b = 2'd0;
        illegal = 1'b0;

        // Decode CSR address (inst[31:20]) to sel number
        case (inst[31:20])
            12'h300: sel = 6'd1;   // mstatus
            12'h301: sel = 6'd2;   // misa
            12'h302: sel = 6'd3;   // medeleg
            12'h303: sel = 6'd4;   // mideleg
            12'h304: sel = 6'd5;   // mie
            12'h305: sel = 6'd6;   // mtvec
            12'h306: sel = 6'd7;   // mcounteren
            12'h340: sel = 6'd8;   // mscratch
            12'h341: sel = 6'd9;   // mepc
            12'h342: sel = 6'd10;  // mcause
            12'h343: sel = 6'd11;  // mtval
            12'h344: sel = 6'd12;  // mip
            12'hB00: sel = 6'd13;  // mcycle
            12'hB02: sel = 6'd14;  // minstret
            12'hB80: sel = 6'd15;  // mcycleh
            12'hB82: sel = 6'd16;  // minstreth
            12'hC00: sel = 6'd17;  // cycle
            12'hC01: sel = 6'd18;  // time
            12'hC02: sel = 6'd19;  // instret
            12'hC80: sel = 6'd20;  // cycleh
            12'hC81: sel = 6'd21;  // timeh
            12'hC82: sel = 6'd22;  // instreth
            12'hF11: sel = 6'd23;  // mvendorid
            12'hF12: sel = 6'd24;  // marchid
            12'hF13: sel = 6'd25;  // mimpid
            12'hF14: sel = 6'd26;  // mhartid
            12'h100: sel = 6'd27;  // sstatus
            12'h104: sel = 6'd28;  // sie
            12'h105: sel = 6'd29;  // stvec
            12'h106: sel = 6'd30;  // scounteren
            12'h140: sel = 6'd31;  // sscratch
            12'h141: sel = 6'd32;  // sepc
            12'h142: sel = 6'd33;  // scause
            12'h143: sel = 6'd34;  // stval
            12'h144: sel = 6'd35;  // sip
            12'h180: sel = 6'd36;  // satp
            12'h7A0: sel = 6'd37;  // tselect
            12'h7A1: sel = 6'd38;  // tdata1
            12'h7A2: sel = 6'd39;  // tdata2
            12'h7A3: sel = 6'd40;  // tdata3
            12'h320: sel = 6'd41;  // mcountinhibit
            12'h3A0: sel = 6'd42;  // pmpcfg0
            12'h3B0: sel = 6'd43;  // pmpaddr0
            default: sel = 6'd0;   // no register
        endcase

        // Determine if this instruction is a CSR access or write
        is_access = (csrop == 3'b001) || (csrop == 3'b010) || (csrop == 3'b011) || (csrop == 3'b100);
        is_write  = (csrop == 3'b010) || (csrop == 3'b011) || (csrop == 3'b100);

        // Check for bad access conditions
        bad = 1'b0;
        if (sel == 6'd0) begin
            bad = 1'b1;                                 // no such register
        end else if (priv < inst[29:28]) begin          // priv < a[9:8]
            bad = 1'b1;
        end else if (is_write && inst[31:30] == 2'b11) begin // write to read-only (a[11:10]==11)
            bad = 1'b1;
        end else if (sel == 6'd36 && priv == 2'b01 && tvm) begin // satp with S-mode and TVM=1
            bad = 1'b1;
        end else if (sel >= 6'd17 && sel <= 6'd22 && priv != 2'b11) begin // counter access from non-M mode
            case (sel)
                6'd17, 6'd20: b = 2'd0; // cycle, cycleh
                6'd18, 6'd21: b = 2'd1; // time, timeh
                6'd19, 6'd22: b = 2'd2; // instret, instreth
                default:      b = 2'd0;
            endcase
            if (mcounteren[b] == 1'b0) begin
                bad = 1'b1;
            end else if (priv == 2'b00 && scounteren[b] == 1'b0) begin
                bad = 1'b1;
            end
        end

        illegal = is_access && bad;
    end

endmodule
