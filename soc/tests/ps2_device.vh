// A PS/2 keyboard or mouse for the testbenches: open-drain clock and data lines, the device clocks every byte (16 kHz at 100 MHz), host-to-device bytes
// (request to send: clock held low for 100 us, then data low and the clock released) are received and acknowledged, and the commands Linux sends at
// probe time are answered. Bytes to send to the host come in through push_ext() (the testbench reads them from a file the GUI server writes).
//   MOUSE=0: AT keyboard (reset FF -> FA AA, get id F2 -> FA AB 83, set LEDs ED, typematic F3, scan code set F0, enable F4, disable F5, echo EE, default FA)
//   MOUSE=1: PS/2 mouse (reset FF -> FA AA 00, get id F2 -> FA 00, sample rate F3, resolution E8, scaling E6/E7, enable F4 starts streaming, disable F5,
//            status E9 -> FA 00 02 64, set defaults F6, remote read EB -> FA; id stays 00: three-byte packets)
module ps2_device #(parameter MOUSE = 0, parameter HALF = 3000) (
  input clk, input rst, input host_clk_low, input host_dat_low, output clk_line, output dat_line);
  reg dclk = 1, ddat = 1;
  assign clk_line = dclk & ~host_clk_low;
  assign dat_line = ddat & ~host_dat_low;
  reg [7:0] q [0:255];
  reg [7:0] qh = 0, qt = 0;
  reg enabled = 0;
  reg [7:0] expect_cmd = 0;   // nonzero: the next byte is the argument of this command
  integer inh = 0, i, nrx_cmds = 0, nbytes_sent = 0;
  reg [10:0] bits;
  reg [7:0] rb;
  reg par;
  task push(input [7:0] b); begin q[qt] = b; qt = qt + 1; end endtask
  task push_ext(input [7:0] b); begin if (MOUSE == 0 || enabled) push(b); end endtask
  task send_byte(input [7:0] b);
    begin
      par = ~(^b);
      bits = {1'b1, par, b, 1'b0};   // stop, parity (odd), data, start; sent from bit 0
      for (i = 0; i < 11; i = i + 1) begin
        ddat = bits[i];
        repeat (HALF) @(posedge clk);
        dclk = 0;
        repeat (HALF) @(posedge clk);
        dclk = 1;
      end
      ddat = 1;
      repeat (HALF) @(posedge clk);
      nbytes_sent = nbytes_sent + 1;
    end
  endtask
  task receive_byte;
    begin
      repeat (HALF) @(posedge clk);   // the host released the clock: let the line settle high before the first pulse (the transmitter must see a falling edge)
      for (i = 0; i < 11; i = i + 1) begin
        dclk = 0;
        repeat (HALF) @(posedge clk);
        dclk = 1;
        bits[i] = dat_line;
        repeat (HALF) @(posedge clk);
      end
      rb = bits[8:1];
      ddat = 0;   // acknowledge
      dclk = 0;
      repeat (HALF) @(posedge clk);
      dclk = 1;
      repeat (HALF) @(posedge clk);
      ddat = 1;
    end
  endtask
  task handle(input [7:0] b);
    begin
      nrx_cmds = nrx_cmds + 1;
      if (expect_cmd != 0) begin
        push(8'hFA);
        expect_cmd = 0;
      end else if (MOUSE == 0) begin
        case (b)
          8'hFF: begin push(8'hFA); push(8'hAA); end
          8'hF2: begin push(8'hFA); push(8'hAB); push(8'h83); end
          8'hED, 8'hF3, 8'hF0: begin push(8'hFA); expect_cmd = b; end
          8'hEE: push(8'hEE);
          default: push(8'hFA);
        endcase
      end else begin
        case (b)
          8'hFF: begin enabled = 0; push(8'hFA); push(8'hAA); push(8'h00); end
          8'hF2: begin push(8'hFA); push(8'h00); end
          8'hF3, 8'hE8: begin push(8'hFA); expect_cmd = b; end
          8'hF4: begin enabled = 1; push(8'hFA); end
          8'hF5, 8'hF6: begin enabled = 0; push(8'hFA); end
          8'hE9: begin push(8'hFA); push(8'h00); push(8'h02); push(8'h64); end
          default: push(8'hFA);
        endcase
      end
    end
  endtask
  initial begin
    forever begin
      @(posedge clk);
      if (rst) begin inh = 0; qh = 0; qt = 0; dclk = 1; ddat = 1; enabled = 0; expect_cmd = 0; end
      else if (host_clk_low) inh = inh + 1;
      else begin
        if (inh > 8000 && host_dat_low) begin
          receive_byte;
          handle(rb);
        end else if (qh != qt && dat_line) begin
          send_byte(q[qh]);
          qh = qh + 1;
        end
        inh = 0;
      end
    end
  end
endmodule
