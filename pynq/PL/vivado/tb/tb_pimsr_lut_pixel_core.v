`timescale 1ns / 1ps

module tb_pimsr_lut_pixel_core;
    reg clk = 1'b0;
    reg rst = 1'b1;
    reg start = 1'b0;

    reg [7:0] left_p0, left_p1, left_p2;
    reg [7:0] right_p0, right_p1, right_p2;
    reg [7:0] top_p0, top_p1, top_p2;
    reg [7:0] bot_p0, bot_p1, bot_p2;

    wire done;
    wire [7:0] out_tl, out_tr, out_bl, out_br;

    localparam LEFT_MEM  = "left_4bit.mem";
    localparam RIGHT_MEM = "right_4bit.mem";
    localparam TOP_MEM   = "top_4bit.mem";
    localparam BOT_MEM   = "bot_4bit.mem";

    pimsr_lut_pixel_core #(
        .LEFT_INIT(LEFT_MEM),
        .RIGHT_INIT(RIGHT_MEM),
        .TOP_INIT(TOP_MEM),
        .BOT_INIT(BOT_MEM)
    ) dut (
        .clk(clk),
        .rst(rst),
        .start(start),

        .left_p0(left_p0),
        .left_p1(left_p1),
        .left_p2(left_p2),
        .right_p0(right_p0),
        .right_p1(right_p1),
        .right_p2(right_p2),
        .top_p0(top_p0),
        .top_p1(top_p1),
        .top_p2(top_p2),
        .bot_p0(bot_p0),
        .bot_p1(bot_p1),
        .bot_p2(bot_p2),

        .done(done),
        .out_tl(out_tl),
        .out_tr(out_tr),
        .out_bl(out_bl),
        .out_br(out_br)
    );

    always #5 clk = ~clk;

    task run_case;
        input [8*32-1:0] name;
        input [7:0] lp0, lp1, lp2;
        input [7:0] rp0, rp1, rp2;
        input [7:0] tp0, tp1, tp2;
        input [7:0] bp0, bp1, bp2;
        integer timeout;
        begin
            left_p0 = lp0; left_p1 = lp1; left_p2 = lp2;
            right_p0 = rp0; right_p1 = rp1; right_p2 = rp2;
            top_p0 = tp0; top_p1 = tp1; top_p2 = tp2;
            bot_p0 = bp0; bot_p1 = bp1; bot_p2 = bp2;

            @(negedge clk);
            start = 1'b1;
            @(posedge clk);
            @(negedge clk);
            start = 1'b0;

            timeout = 0;
            while (!done && timeout < 64) begin
                @(posedge clk);
                timeout = timeout + 1;
            end

            if (!done) begin
                $display("FAIL %0s: done timeout", name);
                $finish;
            end

            if ((^out_tl === 1'bx) || (^out_tr === 1'bx) || (^out_bl === 1'bx) || (^out_br === 1'bx)) begin
                $display("FAIL %0s: output has X/Z tl=%h tr=%h bl=%h br=%h", name, out_tl, out_tr, out_bl, out_br);
                $finish;
            end

            $display("PASS %0s: tl=%0d tr=%0d bl=%0d br=%0d", name, out_tl, out_tr, out_bl, out_br);
            repeat (4) @(posedge clk);
        end
    endtask

    initial begin
        $display("tb_pimsr_lut_pixel_core start");

        left_p0 = 8'd0; left_p1 = 8'd0; left_p2 = 8'd0;
        right_p0 = 8'd0; right_p1 = 8'd0; right_p2 = 8'd0;
        top_p0 = 8'd0; top_p1 = 8'd0; top_p2 = 8'd0;
        bot_p0 = 8'd0; bot_p1 = 8'd0; bot_p2 = 8'd0;

        repeat (5) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;
        repeat (2) @(posedge clk);

        run_case("flat_0", 8'd0, 8'd0, 8'd0, 8'd0, 8'd0, 8'd0, 8'd0, 8'd0, 8'd0, 8'd0, 8'd0, 8'd0);
        run_case("flat_128", 8'd128, 8'd128, 8'd128, 8'd128, 8'd128, 8'd128, 8'd128, 8'd128, 8'd128, 8'd128, 8'd128, 8'd128);
        run_case("mixed_window", 8'd10, 8'd20, 8'd30, 8'd30, 8'd40, 8'd50, 8'd60, 8'd70, 8'd80, 8'd80, 8'd90, 8'd100);

        $display("tb_pimsr_lut_pixel_core done");
        $finish;
    end
endmodule
