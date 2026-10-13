`timescale 1ns / 1ps

module tb_pimsr_image_core;
    localparam IMG_W = 4;
    localparam IMG_H = 4;
    localparam LR_SIZE = IMG_W * IMG_H;
    localparam HR_W = IMG_W * 2;
    localparam HR_H = IMG_H * 2;
    localparam HR_SIZE = HR_W * HR_H;

    localparam LR_FILE = "image_core_lr_4x4.mem";
    localparam HR_GOLDEN_FILE = "image_core_hr_8x8.mem";

    localparam LEFT_MEM  = "left_4bit.mem";
    localparam RIGHT_MEM = "right_4bit.mem";
    localparam TOP_MEM   = "top_4bit.mem";
    localparam BOT_MEM   = "bot_4bit.mem";

    reg clk = 1'b0;
    reg rst = 1'b1;
    reg start = 1'b0;

    wire busy;
    wire done;
    wire [15:0] lr_addr;
    reg [7:0] lr_data;
    wire hr_we;
    wire [17:0] hr_addr;
    wire [7:0] hr_data;

    reg [7:0] lr_mem [0:LR_SIZE-1];
    reg [7:0] hr_mem [0:HR_SIZE-1];
    reg [7:0] hr_golden [0:HR_SIZE-1];

    integer i;
    integer timeout;
    integer errors;
    integer writes;
    reg test_complete = 1'b0;

    pimsr_image_core #(
        .IMG_W(IMG_W),
        .IMG_H(IMG_H),
        .LR_ADDR_WIDTH(16),
        .HR_ADDR_WIDTH(18),
        .LEFT_INIT(LEFT_MEM),
        .RIGHT_INIT(RIGHT_MEM),
        .TOP_INIT(TOP_MEM),
        .BOT_INIT(BOT_MEM)
    ) dut (
        .clk(clk),
        .rst(rst),
        .start(start),
        .busy(busy),
        .done(done),
        .lr_addr(lr_addr),
        .lr_data(lr_data),
        .hr_we(hr_we),
        .hr_addr(hr_addr),
        .hr_data(hr_data)
    );

    always begin
        #5;
        if (test_complete)
            $finish;
        else
            clk = ~clk;
    end

    always @(posedge clk) begin
        if (lr_addr < LR_SIZE)
            lr_data <= lr_mem[lr_addr];
        else
            lr_data <= 8'hxx;

        if (hr_we) begin
            if (hr_addr < HR_SIZE)
                hr_mem[hr_addr] <= hr_data;
            else begin
                $display("FAIL: HR write address out of range: %0d", hr_addr);
                $finish;
            end
        end
    end

    initial begin
        #500000;
        if (!test_complete) begin
            $display("FAIL: global simulation timeout at %0t", $time);
            $display("  busy=%0b done=%0b writes=%0d lr_addr=%0d hr_addr=%0d", busy, done, writes, lr_addr, hr_addr);
            $finish;
        end
    end

    initial begin
        $display("tb_pimsr_image_core start");
        $readmemh(LR_FILE, lr_mem);
        $readmemh(HR_GOLDEN_FILE, hr_golden);

        writes = 0;
        for (i = 0; i < HR_SIZE; i = i + 1)
            hr_mem[i] = 8'h00;

        repeat (5) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        @(negedge clk);
        start = 1'b1;
        @(posedge clk);
        @(negedge clk);
        start = 1'b0;

        timeout = 0;
        while (!done && timeout < 10000) begin
            @(posedge clk);
            if (hr_we)
                writes = writes + 1;
            timeout = timeout + 1;
        end

        if (!done) begin
            $display("FAIL: image core done timeout after %0d cycles, writes=%0d", timeout, writes);
            $finish;
        end

        errors = 0;
        for (i = 0; i < HR_SIZE; i = i + 1) begin
            if (hr_mem[i] !== hr_golden[i]) begin
                $display("MISMATCH addr=%0d expected=%0d got=%0d", i, hr_golden[i], hr_mem[i]);
                errors = errors + 1;
            end
        end

        if (errors == 0)
            $display("PASS: image core HR output matched %0d pixels", HR_SIZE);
        else begin
            $display("FAIL: image core had %0d mismatches", errors);
            $finish;
        end

        $display("tb_pimsr_image_core done");
        test_complete = 1'b1;
        $finish;
    end
endmodule
