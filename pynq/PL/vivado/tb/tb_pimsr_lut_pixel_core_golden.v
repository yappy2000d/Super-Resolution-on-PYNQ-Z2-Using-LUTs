`timescale 1ns / 1ps

module tb_pimsr_lut_pixel_core_golden;
    localparam integer VEC_COUNT = 262;
    localparam VECTOR_FILE = "pixel_core_vectors.mem";

    reg clk = 1'b0;
    reg rst = 1'b1;
    reg start = 1'b0;

    reg [7:0] left_p0, left_p1, left_p2;
    reg [7:0] right_p0, right_p1, right_p2;
    reg [7:0] top_p0, top_p1, top_p2;
    reg [7:0] bot_p0, bot_p1, bot_p2;

    wire done;
    wire [7:0] out_tl, out_tr, out_bl, out_br;

    reg [127:0] vectors [0:VEC_COUNT-1];
    reg [127:0] vec;
    reg [7:0] exp_tl, exp_tr, exp_bl, exp_br;

    integer i;
    integer timeout;
    integer wait_cycles;
    integer pass_count;
    reg seen_done;
    reg test_complete = 1'b0;

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

    always begin
        #5;
        if (test_complete)
            $finish;
        else
            clk = ~clk;
    end

    initial begin
        #500000;
        if (!test_complete) begin
            $display("FAIL: global simulation timeout at %0t", $time);
            $display("  vector=%0d pass_count=%0d done=%0b", i, pass_count, done);
            $display("  outputs tl=%0d tr=%0d bl=%0d br=%0d", out_tl, out_tr, out_bl, out_br);
            $finish;
        end
    end

    task fail_case;
        input integer idx;
        begin
            $display("FAIL vector %0d", idx);
            $display("  inputs left=(%0d,%0d,%0d) right=(%0d,%0d,%0d) top=(%0d,%0d,%0d) bot=(%0d,%0d,%0d)",
                left_p0, left_p1, left_p2,
                right_p0, right_p1, right_p2,
                top_p0, top_p1, top_p2,
                bot_p0, bot_p1, bot_p2);
            $display("  expected tl=%0d tr=%0d bl=%0d br=%0d", exp_tl, exp_tr, exp_bl, exp_br);
            $display("  got      tl=%0d tr=%0d bl=%0d br=%0d", out_tl, out_tr, out_bl, out_br);
            $finish;
        end
    endtask

    initial begin
        $display("tb_pimsr_lut_pixel_core_golden start");
        $readmemh(VECTOR_FILE, vectors);

        left_p0 = 8'd0; left_p1 = 8'd0; left_p2 = 8'd0;
        right_p0 = 8'd0; right_p1 = 8'd0; right_p2 = 8'd0;
        top_p0 = 8'd0; top_p1 = 8'd0; top_p2 = 8'd0;
        bot_p0 = 8'd0; bot_p1 = 8'd0; bot_p2 = 8'd0;

        repeat (5) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;
        pass_count = 0;

        for (i = 0; i < VEC_COUNT; i = i + 1) begin
            vec = vectors[i];

            @(negedge clk);
            left_p0  = vec[127:120];
            left_p1  = vec[119:112];
            left_p2  = vec[111:104];
            right_p0 = vec[103:96];
            right_p1 = vec[95:88];
            right_p2 = vec[87:80];
            top_p0   = vec[79:72];
            top_p1   = vec[71:64];
            top_p2   = vec[63:56];
            bot_p0   = vec[55:48];
            bot_p1   = vec[47:40];
            bot_p2   = vec[39:32];
            exp_tl   = vec[31:24];
            exp_tr   = vec[23:16];
            exp_bl   = vec[15:8];
            exp_br   = vec[7:0];

            start = 1'b1;
            @(posedge clk);
            @(negedge clk);
            start = 1'b0;

            seen_done = 1'b0;
            timeout = 0;
            for (wait_cycles = 0; wait_cycles < 128; wait_cycles = wait_cycles + 1) begin
                @(posedge clk);
                if (done === 1'b1) begin
                    seen_done = 1'b1;
                    timeout = wait_cycles + 1;
                    wait_cycles = 128;
                end
            end

            if (!seen_done) begin
                $display("FAIL vector %0d: done timeout, done=%0b", i, done);
                $finish;
            end

            if ((out_tl !== exp_tl) || (out_tr !== exp_tr) || (out_bl !== exp_bl) || (out_br !== exp_br))
                fail_case(i);

            pass_count = pass_count + 1;
            repeat (2) @(posedge clk);
        end

        $display("PASS: %0d/%0d vectors matched", pass_count, VEC_COUNT);
        $display("tb_pimsr_lut_pixel_core_golden done");
        test_complete = 1'b1;
        $finish;
    end
endmodule
