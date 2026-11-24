// Self-checking testbench for barg_fpu: every line of the vector file (tb/gen_fpu_vectors.py, from the exact reference model) is run on the unit and the
// result, the integer result (when the operation gives one) and the flags are compared. +VEC=<file>. Prints "PASS" or "FAIL <what>" (the first few failures are
// described). Written for Verilator.
module tb_fpu;
  parameter integer SEED = 1;
  reg clk = 0, rst = 1, start = 0, dbl = 0;
  reg [4:0] op = 0; reg [2:0] rm = 0; reg [63:0] a = 0, b = 0, c = 0; reg [31:0] ia = 0;
  wire busy, done, wr_f; wire [63:0] fres; wire [31:0] ires; wire [4:0] flags;
  barg_fpu dut (.clk(clk), .rst(rst), .start(start), .op(op), .dbl(dbl), .rm(rm), .a(a), .b(b), .c(c), .ia(ia), .busy(busy), .done(done), .fres(fres), .ires(ires),
                .flags(flags), .wr_f(wr_f));
  always #5 clk = ~clk;
  integer fd, r, n, errors, wait_n;
  reg [1023:0] vecfile;
  reg [4:0] v_op; reg v_dbl; reg [2:0] v_rm; reg [63:0] v_a, v_b, v_c, v_fres; reg [31:0] v_ia, v_ires; reg [4:0] v_flags; reg v_wr;
  initial begin
    errors = 0; n = 0;
    if (!$value$plusargs("VEC=%s", vecfile)) begin $display("FAIL no +VEC"); $finish; end
    fd = $fopen(vecfile, "r");
    if (fd == 0) begin $display("FAIL cannot open the vector file"); $finish; end
    repeat (3) @(posedge clk);
    rst <= 0;
    @(posedge clk);
    while (!$feof(fd)) begin
      r = $fscanf(fd, "%h %h %h %h %h %h %h %h %h %h %h\n", v_op, v_dbl, v_rm, v_a, v_b, v_c, v_ia, v_fres, v_ires, v_flags, v_wr);
      if (r == 11) begin
        @(negedge clk);
        op = v_op; dbl = v_dbl; rm = v_rm; a = v_a; b = v_b; c = v_c; ia = v_ia; start = 1;
        @(negedge clk);
        start = 0;
        wait_n = 0;
        while (!done && wait_n < 200) begin @(negedge clk); wait_n = wait_n + 1; end
        n = n + 1;
        if (!done) begin $display("FAIL timeout: op %0h dbl %0h", v_op, v_dbl); errors = errors + 1; end
        else if (wr_f !== v_wr || flags !== v_flags || (v_wr ? (fres !== v_fres) : (ires !== v_ires))) begin
          errors = errors + 1;
          if (errors <= 6)
            $display("FAIL op %0h dbl %0h rm %0h a %h b %h c %h ia %h: got res %h ires %h flags %h wr %h, want res %h ires %h flags %h wr %h",
                     v_op, v_dbl, v_rm, v_a, v_b, v_c, v_ia, fres, ires, flags, wr_f, v_fres, v_ires, v_flags, v_wr);
        end
        @(negedge clk);
      end
    end
    $fclose(fd);
    if (errors == 0) $display("PASS %0d vectors", n); else $display("FAIL %0d of %0d vectors", errors, n);
    $finish;
  end
endmodule
