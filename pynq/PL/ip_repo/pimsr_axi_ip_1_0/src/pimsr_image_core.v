`timescale 1ns / 1ps

module pimsr_image_core #(
    parameter IMG_W = 45,
    parameter IMG_H = 45,
    parameter LR_ADDR_WIDTH = 16,
    parameter HR_ADDR_WIDTH = 18,
    parameter LEFT_INIT  = "left_4bit.mem",
    parameter RIGHT_INIT = "right_4bit.mem",
    parameter TOP_INIT   = "top_4bit.mem",
    parameter BOT_INIT   = "bot_4bit.mem"
) (
    input  wire                      clk,
    input  wire                      rst,
    input  wire                      start,

    output reg                       busy,
    output reg                       done,

    output reg  [LR_ADDR_WIDTH-1:0]  lr_addr,
    input  wire [7:0]                lr_data,

    output reg                       hr_we,
    output reg  [HR_ADDR_WIDTH-1:0]  hr_addr,
    output reg  [7:0]                hr_data
);
    localparam S_IDLE       = 4'd0;
    localparam S_SET_ADDR   = 4'd1;
    localparam S_WAIT_DATA  = 4'd2;
    localparam S_CAPTURE    = 4'd3;
    localparam S_START_CORE = 4'd4;
    localparam S_WAIT_CORE  = 4'd5;
    localparam S_WRITE_TL   = 4'd6;
    localparam S_WRITE_TR   = 4'd7;
    localparam S_WRITE_BL   = 4'd8;
    localparam S_WRITE_BR   = 4'd9;
    localparam S_NEXT       = 4'd10;
    localparam S_DONE       = 4'd11;

    reg [3:0] state;
    reg [3:0] sample_idx;
    reg core_start;

    reg [15:0] x;
    reg [15:0] y;

    reg [7:0] left_p0, left_p1, left_p2;
    reg [7:0] right_p0, right_p1, right_p2;
    reg [7:0] top_p0, top_p1, top_p2;
    reg [7:0] bot_p0, bot_p1, bot_p2;

    wire core_done;
    wire [7:0] out_tl, out_tr, out_bl, out_br;

    pimsr_lut_pixel_core #(
        .LEFT_INIT(LEFT_INIT),
        .RIGHT_INIT(RIGHT_INIT),
        .TOP_INIT(TOP_INIT),
        .BOT_INIT(BOT_INIT)
    ) pixel_core_i (
        .clk(clk),
        .rst(rst),
        .start(core_start),

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

        .done(core_done),
        .out_tl(out_tl),
        .out_tr(out_tr),
        .out_bl(out_bl),
        .out_br(out_br)
    );

    function [15:0] clamp_coord;
        input [15:0] coord;
        input signed [3:0] delta;
        input [15:0] limit;
        reg signed [31:0] tmp;
        begin
            tmp = $signed({1'b0, coord}) + delta;
            if (tmp < 0)
                clamp_coord = 16'd0;
            else if (tmp >= limit)
                clamp_coord = limit - 16'd1;
            else
                clamp_coord = tmp[15:0];
        end
    endfunction

    function [LR_ADDR_WIDTH-1:0] lr_linear_addr;
        input [15:0] px;
        input [15:0] py;
        begin
            lr_linear_addr = (py * IMG_W) + px;
        end
    endfunction

    function [HR_ADDR_WIDTH-1:0] hr_base_addr;
        input [15:0] px;
        input [15:0] py;
        begin
            hr_base_addr = ((py << 1) * (IMG_W << 1)) + (px << 1);
        end
    endfunction

    function [LR_ADDR_WIDTH-1:0] sample_addr;
        input [3:0] idx;
        reg [15:0] sx;
        reg [15:0] sy;
        begin
            case (idx)
                4'd0: begin sx = clamp_coord(x, -4'sd2, IMG_W); sy = y; end
                4'd1: begin sx = clamp_coord(x, -4'sd1, IMG_W); sy = y; end
                4'd2: begin sx = x; sy = y; end
                4'd3: begin sx = x; sy = y; end
                4'd4: begin sx = clamp_coord(x, 4'sd1, IMG_W); sy = y; end
                4'd5: begin sx = clamp_coord(x, 4'sd2, IMG_W); sy = y; end
                4'd6: begin sx = x; sy = clamp_coord(y, -4'sd2, IMG_H); end
                4'd7: begin sx = x; sy = clamp_coord(y, -4'sd1, IMG_H); end
                4'd8: begin sx = x; sy = y; end
                4'd9: begin sx = x; sy = y; end
                4'd10: begin sx = x; sy = clamp_coord(y, 4'sd1, IMG_H); end
                default: begin sx = x; sy = clamp_coord(y, 4'sd2, IMG_H); end
            endcase
            sample_addr = lr_linear_addr(sx, sy);
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            sample_idx <= 4'd0;
            core_start <= 1'b0;
            busy <= 1'b0;
            done <= 1'b0;
            lr_addr <= {LR_ADDR_WIDTH{1'b0}};
            hr_we <= 1'b0;
            hr_addr <= {HR_ADDR_WIDTH{1'b0}};
            hr_data <= 8'd0;
            x <= 16'd0;
            y <= 16'd0;
            left_p0 <= 8'd0; left_p1 <= 8'd0; left_p2 <= 8'd0;
            right_p0 <= 8'd0; right_p1 <= 8'd0; right_p2 <= 8'd0;
            top_p0 <= 8'd0; top_p1 <= 8'd0; top_p2 <= 8'd0;
            bot_p0 <= 8'd0; bot_p1 <= 8'd0; bot_p2 <= 8'd0;
        end else begin
            done <= 1'b0;
            hr_we <= 1'b0;
            core_start <= 1'b0;

            case (state)
                S_IDLE: begin
                    if (start) begin
                        busy <= 1'b1;
                        x <= 16'd0;
                        y <= 16'd0;
                        sample_idx <= 4'd0;
                        state <= S_SET_ADDR;
                    end
                end

                S_SET_ADDR: begin
                    lr_addr <= sample_addr(sample_idx);
                    state <= S_WAIT_DATA;
                end

                S_WAIT_DATA: begin
                    state <= S_CAPTURE;
                end

                S_CAPTURE: begin
                    case (sample_idx)
                        4'd0: left_p0 <= lr_data;
                        4'd1: left_p1 <= lr_data;
                        4'd2: left_p2 <= lr_data;
                        4'd3: right_p0 <= lr_data;
                        4'd4: right_p1 <= lr_data;
                        4'd5: right_p2 <= lr_data;
                        4'd6: top_p0 <= lr_data;
                        4'd7: top_p1 <= lr_data;
                        4'd8: top_p2 <= lr_data;
                        4'd9: bot_p0 <= lr_data;
                        4'd10: bot_p1 <= lr_data;
                        default: bot_p2 <= lr_data;
                    endcase

                    if (sample_idx == 4'd11) begin
                        state <= S_START_CORE;
                    end else begin
                        sample_idx <= sample_idx + 4'd1;
                        state <= S_SET_ADDR;
                    end
                end

                S_START_CORE: begin
                    core_start <= 1'b1;
                    state <= S_WAIT_CORE;
                end

                S_WAIT_CORE: begin
                    if (core_done)
                        state <= S_WRITE_TL;
                end

                S_WRITE_TL: begin
                    hr_we <= 1'b1;
                    hr_addr <= hr_base_addr(x, y);
                    hr_data <= out_tl;
                    state <= S_WRITE_TR;
                end

                S_WRITE_TR: begin
                    hr_we <= 1'b1;
                    hr_addr <= hr_base_addr(x, y) + 1;
                    hr_data <= out_tr;
                    state <= S_WRITE_BL;
                end

                S_WRITE_BL: begin
                    hr_we <= 1'b1;
                    hr_addr <= hr_base_addr(x, y) + (IMG_W << 1);
                    hr_data <= out_bl;
                    state <= S_WRITE_BR;
                end

                S_WRITE_BR: begin
                    hr_we <= 1'b1;
                    hr_addr <= hr_base_addr(x, y) + (IMG_W << 1) + 1;
                    hr_data <= out_br;
                    state <= S_NEXT;
                end

                S_NEXT: begin
                    if (x == IMG_W - 1) begin
                        x <= 16'd0;
                        if (y == IMG_H - 1) begin
                            state <= S_DONE;
                        end else begin
                            y <= y + 16'd1;
                            sample_idx <= 4'd0;
                            state <= S_SET_ADDR;
                        end
                    end else begin
                        x <= x + 16'd1;
                        sample_idx <= 4'd0;
                        state <= S_SET_ADDR;
                    end
                end

                S_DONE: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    state <= S_IDLE;
                end
            endcase
        end
    end
endmodule
