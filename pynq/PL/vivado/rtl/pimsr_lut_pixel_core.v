`timescale 1ns / 1ps

module pimsr_lut_pixel_core #(
    parameter LEFT_INIT  = "left_4bit.mem",
    parameter RIGHT_INIT = "right_4bit.mem",
    parameter TOP_INIT   = "top_4bit.mem",
    parameter BOT_INIT   = "bot_4bit.mem"
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       start,

    input  wire [7:0] left_p0,
    input  wire [7:0] left_p1,
    input  wire [7:0] left_p2,
    input  wire [7:0] right_p0,
    input  wire [7:0] right_p1,
    input  wire [7:0] right_p2,
    input  wire [7:0] top_p0,
    input  wire [7:0] top_p1,
    input  wire [7:0] top_p2,
    input  wire [7:0] bot_p0,
    input  wire [7:0] bot_p1,
    input  wire [7:0] bot_p2,

    output reg        done,
    output reg [7:0]  out_tl,
    output reg [7:0]  out_tr,
    output reg [7:0]  out_bl,
    output reg [7:0]  out_br
);
    wire left_done, right_done, top_done, bot_done;
    wire signed [15:0] ly0, ly1, ly2, ly3;
    wire signed [15:0] ry0, ry1, ry2, ry3;
    wire signed [15:0] ty0, ty1, ty2, ty3;
    wire signed [15:0] by0, by1, by2, by3;

    reg busy;

    pimsr_branch_interp_seq #(.INIT_FILE(LEFT_INIT)) left_i (
        .clk(clk), .rst(rst), .start(start && !busy),
        .p0(left_p0), .p1(left_p1), .p2(left_p2),
        .done(left_done), .y0(ly0), .y1(ly1), .y2(ly2), .y3(ly3)
    );

    pimsr_branch_interp_seq #(.INIT_FILE(RIGHT_INIT)) right_i (
        .clk(clk), .rst(rst), .start(start && !busy),
        .p0(right_p0), .p1(right_p1), .p2(right_p2),
        .done(right_done), .y0(ry0), .y1(ry1), .y2(ry2), .y3(ry3)
    );

    pimsr_branch_interp_seq #(.INIT_FILE(TOP_INIT)) top_i (
        .clk(clk), .rst(rst), .start(start && !busy),
        .p0(top_p0), .p1(top_p1), .p2(top_p2),
        .done(top_done), .y0(ty0), .y1(ty1), .y2(ty2), .y3(ty3)
    );

    pimsr_branch_interp_seq #(.INIT_FILE(BOT_INIT)) bot_i (
        .clk(clk), .rst(rst), .start(start && !busy),
        .p0(bot_p0), .p1(bot_p1), .p2(bot_p2),
        .done(bot_done), .y0(by0), .y1(by1), .y2(by2), .y3(by3)
    );

    function [7:0] clamp_u8;
        input signed [17:0] v;
        begin
            if (v < 0)
                clamp_u8 = 8'd0;
            else if (v > 18'sd255)
                clamp_u8 = 8'd255;
            else
                clamp_u8 = v[7:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0;
            done <= 1'b0;
            out_tl <= 8'd0;
            out_tr <= 8'd0;
            out_bl <= 8'd0;
            out_br <= 8'd0;
        end else begin
            done <= 1'b0;
            if (start && !busy)
                busy <= 1'b1;

            if (busy && left_done && right_done && top_done && bot_done) begin
                out_tl <= clamp_u8($signed(ly0) + $signed(ry0) + $signed(ty0) + $signed(by0));
                out_tr <= clamp_u8($signed(ly1) + $signed(ry1) + $signed(ty1) + $signed(by1));
                out_bl <= clamp_u8($signed(ly2) + $signed(ry2) + $signed(ty2) + $signed(by2));
                out_br <= clamp_u8($signed(ly3) + $signed(ry3) + $signed(ty3) + $signed(by3));
                done <= 1'b1;
                busy <= 1'b0;
            end
        end
    end
endmodule
