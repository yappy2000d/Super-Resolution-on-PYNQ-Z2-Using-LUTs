`timescale 1ns / 1ps

module pimsr_branch_interp_seq #(
    parameter INIT_FILE = "left_4bit.mem"
) (
    input  wire              clk,
    input  wire              rst,
    input  wire              start,
    input  wire [7:0]        p0,
    input  wire [7:0]        p1,
    input  wire [7:0]        p2,
    output reg               done,
    output reg signed [15:0] y0,
    output reg signed [15:0] y1,
    output reg signed [15:0] y2,
    output reg signed [15:0] y3
);
    localparam S_IDLE      = 5'd0;
    localparam S_ADDR0     = 5'd1;
    localparam S_ADDR1     = 5'd2;
    localparam S_ADDR2     = 5'd3;
    localparam S_ADDR3     = 5'd4;
    localparam S_ADDR4     = 5'd5;
    localparam S_ADDR5     = 5'd6;
    localparam S_ADDR6     = 5'd7;
    localparam S_ADDR7     = 5'd8;
    localparam S_LOAD111   = 5'd9;
    localparam S_PREP_CH   = 5'd10;
    localparam S_TERM1_MUL = 5'd11;
    localparam S_TERM1_ACC = 5'd12;
    localparam S_TERM2_MUL = 5'd13;
    localparam S_TERM2_ACC = 5'd14;
    localparam S_TERM3_MUL = 5'd15;
    localparam S_TERM3_ACC = 5'd16;
    localparam S_STORE     = 5'd17;
    localparam S_DONE      = 5'd18;

    reg [4:0] state;
    reg [1:0] calc_ch;
    reg [11:0] rom_addr;
    wire [31:0] rom_data;

    reg [3:0] i0, i1, i2;
    reg [3:0] h0, h1, h2;
    reg [4:0] f0, f1, f2;

    reg [31:0] v000, v100, v010, v001, v110, v101, v011, v111;
    reg signed [15:0] base_r, first_r, second_r, third_r;
    reg [4:0] w1_r, w2_r, w3_r;
    reg signed [31:0] acc_r;
    reg signed [31:0] term_r;

    pimsr_sampled_lut_rom #(
        .INIT_FILE(INIT_FILE)
    ) rom_i (
        .clk(clk),
        .addr(rom_addr),
        .data(rom_data)
    );

    function [11:0] pack_addr;
        input [3:0] a;
        input [3:0] b;
        input [3:0] c;
        begin
            pack_addr = {a, b, c};
        end
    endfunction

    function signed [15:0] sx8;
        input [7:0] v;
        begin
            sx8 = {{8{v[7]}}, v};
        end
    endfunction

    function signed [15:0] word_ch;
        input [31:0] word;
        input [1:0] ch;
        begin
            case (ch)
                2'd0: word_ch = sx8(word[31:24]);
                2'd1: word_ch = sx8(word[23:16]);
                2'd2: word_ch = sx8(word[15:8]);
                default: word_ch = sx8(word[7:0]);
            endcase
        end
    endfunction

    function signed [31:0] round_shift4;
        input signed [31:0] v;
        begin
            if (v >= 0)
                round_shift4 = (v + 32'sd8) >>> 4;
            else
                round_shift4 = (v - 32'sd8) >>> 4;
        end
    endfunction

    function signed [31:0] weighted_delta;
        input [4:0] w;
        input signed [15:0] a;
        input signed [15:0] b;
        reg signed [16:0] diff;
        reg signed [22:0] product;
        begin
            diff = a - b;
            product = $signed({1'b0, w}) * diff;
            weighted_delta = round_shift4({{9{product[22]}}, product});
        end
    endfunction

    function signed [15:0] clamp_s8_to_s16;
        input signed [31:0] v;
        begin
            if (v > 32'sd127)
                clamp_s8_to_s16 = 16'sd127;
            else if (v < -32'sd128)
                clamp_s8_to_s16 = -16'sd128;
            else
                clamp_s8_to_s16 = v[15:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            done <= 1'b0;
            y0 <= 16'sd0;
            y1 <= 16'sd0;
            y2 <= 16'sd0;
            y3 <= 16'sd0;
            calc_ch <= 2'd0;
            rom_addr <= 12'd0;
            base_r <= 16'sd0;
            first_r <= 16'sd0;
            second_r <= 16'sd0;
            third_r <= 16'sd0;
            w1_r <= 5'd0;
            w2_r <= 5'd0;
            w3_r <= 5'd0;
            acc_r <= 32'sd0;
            term_r <= 32'sd0;
        end else begin
            done <= 1'b0;
            case (state)
                S_IDLE: begin
                    if (start) begin
                        i0 <= p0[7:4];
                        i1 <= p1[7:4];
                        i2 <= p2[7:4];
                        h0 <= (p0[7:4] == 4'hf) ? 4'hf : (p0[7:4] + 4'd1);
                        h1 <= (p1[7:4] == 4'hf) ? 4'hf : (p1[7:4] + 4'd1);
                        h2 <= (p2[7:4] == 4'hf) ? 4'hf : (p2[7:4] + 4'd1);
                        f0 <= (p0[7:4] == 4'hf) ? 5'd0 : {1'b0, p0[3:0]};
                        f1 <= (p1[7:4] == 4'hf) ? 5'd0 : {1'b0, p1[3:0]};
                        f2 <= (p2[7:4] == 4'hf) ? 5'd0 : {1'b0, p2[3:0]};
                        rom_addr <= pack_addr(p0[7:4], p1[7:4], p2[7:4]);
                        state <= S_ADDR0;
                    end
                end

                S_ADDR0: begin rom_addr <= pack_addr(h0, i1, i2); state <= S_ADDR1; end
                S_ADDR1: begin v000 <= rom_data; rom_addr <= pack_addr(i0, h1, i2); state <= S_ADDR2; end
                S_ADDR2: begin v100 <= rom_data; rom_addr <= pack_addr(i0, i1, h2); state <= S_ADDR3; end
                S_ADDR3: begin v010 <= rom_data; rom_addr <= pack_addr(h0, h1, i2); state <= S_ADDR4; end
                S_ADDR4: begin v001 <= rom_data; rom_addr <= pack_addr(h0, i1, h2); state <= S_ADDR5; end
                S_ADDR5: begin v110 <= rom_data; rom_addr <= pack_addr(i0, h1, h2); state <= S_ADDR6; end
                S_ADDR6: begin v101 <= rom_data; rom_addr <= pack_addr(h0, h1, h2); state <= S_ADDR7; end
                S_ADDR7: begin v011 <= rom_data; state <= S_LOAD111; end

                S_LOAD111: begin
                    v111 <= rom_data;
                    calc_ch <= 2'd0;
                    state <= S_PREP_CH;
                end

                S_PREP_CH: begin
                    base_r <= word_ch(v000, calc_ch);
                    third_r <= word_ch(v111, calc_ch);
                    acc_r <= word_ch(v000, calc_ch);

                    if ((f0 >= f1) && (f1 >= f2)) begin
                        first_r <= word_ch(v100, calc_ch);
                        second_r <= word_ch(v110, calc_ch);
                        w1_r <= f0; w2_r <= f1; w3_r <= f2;
                    end else if ((f0 >= f2) && (f2 > f1)) begin
                        first_r <= word_ch(v100, calc_ch);
                        second_r <= word_ch(v101, calc_ch);
                        w1_r <= f0; w2_r <= f2; w3_r <= f1;
                    end else if ((f1 > f0) && (f0 >= f2)) begin
                        first_r <= word_ch(v010, calc_ch);
                        second_r <= word_ch(v110, calc_ch);
                        w1_r <= f1; w2_r <= f0; w3_r <= f2;
                    end else if ((f1 >= f2) && (f2 > f0)) begin
                        first_r <= word_ch(v010, calc_ch);
                        second_r <= word_ch(v011, calc_ch);
                        w1_r <= f1; w2_r <= f2; w3_r <= f0;
                    end else if ((f2 > f0) && (f0 >= f1)) begin
                        first_r <= word_ch(v001, calc_ch);
                        second_r <= word_ch(v101, calc_ch);
                        w1_r <= f2; w2_r <= f0; w3_r <= f1;
                    end else begin
                        first_r <= word_ch(v001, calc_ch);
                        second_r <= word_ch(v011, calc_ch);
                        w1_r <= f2; w2_r <= f1; w3_r <= f0;
                    end

                    state <= S_TERM1_MUL;
                end

                S_TERM1_MUL: begin
                    term_r <= weighted_delta(w1_r, first_r, base_r);
                    state <= S_TERM1_ACC;
                end

                S_TERM1_ACC: begin
                    acc_r <= acc_r + term_r;
                    state <= S_TERM2_MUL;
                end

                S_TERM2_MUL: begin
                    term_r <= weighted_delta(w2_r, second_r, first_r);
                    state <= S_TERM2_ACC;
                end

                S_TERM2_ACC: begin
                    acc_r <= acc_r + term_r;
                    state <= S_TERM3_MUL;
                end

                S_TERM3_MUL: begin
                    term_r <= weighted_delta(w3_r, third_r, second_r);
                    state <= S_TERM3_ACC;
                end

                S_TERM3_ACC: begin
                    acc_r <= acc_r + term_r;
                    state <= S_STORE;
                end

                S_STORE: begin
                    case (calc_ch)
                        2'd0: y0 <= clamp_s8_to_s16(acc_r);
                        2'd1: y1 <= clamp_s8_to_s16(acc_r);
                        2'd2: y2 <= clamp_s8_to_s16(acc_r);
                        default: y3 <= clamp_s8_to_s16(acc_r);
                    endcase

                    if (calc_ch == 2'd3) begin
                        state <= S_DONE;
                    end else begin
                        calc_ch <= calc_ch + 2'd1;
                        state <= S_PREP_CH;
                    end
                end

                S_DONE: begin
                    done <= 1'b1;
                    state <= S_IDLE;
                end
            endcase
        end
    end
endmodule
