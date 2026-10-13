`timescale 1ns / 1ps

module pimsr_sampled_lut_rom #(
    parameter INIT_FILE = "left_4bit.mem"
) (
    input  wire        clk,
    input  wire [11:0] addr,
    output reg  [31:0] data
);
    (* rom_style = "block" *) reg [31:0] mem [0:4095];

    initial begin
        $readmemh(INIT_FILE, mem);
    end

    always @(posedge clk) begin
        data <= mem[addr];
    end
endmodule
