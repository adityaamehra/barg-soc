module perm_check (
    input  wire [1:0] kind,
    input  wire [1:0] priv,
    input  wire       sum,
    input  wire       mxr,
    input  wire [7:0] flags,
    output wire       fault
);

    wire V = flags[0];
    wire R = flags[1];
    wire W = flags[2];
    wire X = flags[3];
    wire U = flags[4];
    wire G = flags[5];
    wire A = flags[6];
    wire D = flags[7];

    wire is_machine = (priv == 2'b11);
    wire is_user    = (priv == 2'b00);
    wire is_super   = (priv == 2'b01);

    wire fetch  = (kind == 2'b00);
    wire load   = (kind == 2'b01);
    wire store  = (kind == 2'b10) || (kind == 2'b11);

    wire fault_user_u   = is_user  && !U;
    wire fault_super_u  = is_super &&  U && (fetch || !sum);
    wire fault_perm     = (fetch && !X) ||
                          (load  && !R && !(X && mxr)) ||
                          (store && !W);
    wire fault_A        = !A;
    wire fault_D        = store && !D;

    assign fault = is_machine ? 1'b0 :
                   (fault_user_u || fault_super_u || fault_perm || fault_A || fault_D);

endmodule
