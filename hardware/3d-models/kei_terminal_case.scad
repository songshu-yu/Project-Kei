// ============================================================
// Project Kei — 赛博女友终端外壳
// Cyberpunk-style Raspberry Pi 5 Terminal Case
//
// 使用方法:
//   1. 下载 OpenSCAD: https://openscad.org/downloads.html
//   2. 打开此文件
//   3. 按 F5 预览 / F6 渲染
//   4. File → Export → STL 导出打印
//
// 打印建议:
//   材质: PETG（耐热）或 PLA（好打）
//   层高: 0.2mm
//   填充: 20%
//   支撑: 需要（屏幕窗口处）
// ============================================================

// === 全局参数（按需调整）===
$fn = 60;  // 圆的细分度，渲染时可改成 120

// --- 树莓派 5 尺寸 ---
pi_w = 85;        // 板宽 (mm)
pi_d = 56;        // 板深
pi_h = 23;        // 板高（含接口）
pi_mount_inset_x = 3.5;   // 安装孔 X 偏移
pi_mount_inset_y = 3.5;   // 安装孔 Y 偏移
pi_mount_dx = 58;          // 安装孔 X 间距
pi_mount_dy = 49;          // 安装孔 Y 间距

// --- 外壳主体 ---
wall = 2.5;           // 壁厚
clearance = 1.5;      // 板子四周间隙
case_w = pi_w + clearance*2 + wall*2;   // ~95mm
case_d = pi_d + clearance*2 + wall*2;   // ~66mm
case_h_bottom = 18;   // 下壳高度
case_h_top = 30;      // 上壳高度（含屏幕空间）
case_r = 4;           // 圆角半径
bevel = 3;            // 赛博朋克倒角

// --- 屏幕 ---
screen_enabled = true;
screen_diameter = 40;     // 圆形屏幕直径 (GC9A01 常见 1.28寸 = ~35mm)
screen_offset_y = 5;      // 屏幕在正面的 Y 偏移

// --- 扬声器 ---
speaker_side = "right";   // 扬声器在哪一侧: "left" / "right" / "both"
speaker_grille_w = 30;
speaker_grille_h = 15;

// --- LED 灯带槽 ---
led_strip_w = 10;     // WS2812B 灯带宽度
led_strip_d = 3;      // 灯带槽深度
led_enabled = true;

// --- 散热 ---
fan_size = 30;         // 散热风扇尺寸 (30mm)
fan_mount = true;

// ============================================================
// 主体模块
// ============================================================

// 选择要渲染的部分（打印时分别导出）
// 取消注释你要打印的部分:

bottom_case();
translate([0, 0, case_h_bottom + 5]) top_case();

// 单独导出时用:
// bottom_case();
// top_case();

// ============================================================
// 下壳
// ============================================================
module bottom_case() {
    difference() {
        union() {
            // 主体
            rounded_box(case_w, case_d, case_h_bottom, case_r);

            // 底部脚垫凸台
            for (pos = corner_positions(case_w - 10, case_d - 10)) {
                translate([pos[0], pos[1], 0])
                    cylinder(h=1.5, r=4);
            }
        }

        // 挖空内部
        translate([wall, wall, wall])
            rounded_box(case_w - wall*2, case_d - wall*2, case_h_bottom, case_r - 1);

        // --- 接口开孔（树莓派 5 的接口在两侧）---

        // USB + Ethernet 侧 (X+ 方向)
        // USB-A x2
        translate([case_w - wall - 0.5, wall + clearance + 29, wall + 3])
            cube([wall + 1, 15, 16]);
        // Ethernet
        translate([case_w - wall - 0.5, wall + clearance + 45, wall + 3])
            cube([wall + 1, 16, 14]);

        // 电源 + HDMI 侧 (Y 方向)
        // USB-C 电源
        translate([wall + clearance + 7, -0.5, wall + 3])
            cube([10, wall + 1, 4]);
        // micro HDMI x2
        translate([wall + clearance + 22, -0.5, wall + 3])
            cube([8, wall + 1, 4]);
        translate([wall + clearance + 35, -0.5, wall + 3])
            cube([8, wall + 1, 4]);

        // SD 卡侧 (X- 方向)
        translate([-0.5, wall + clearance + 20, wall + 1])
            cube([wall + 1, 14, 3]);

        // 扬声器格栅
        if (speaker_side == "right" || speaker_side == "both") {
            translate([case_w - wall - 0.5, (case_d - speaker_grille_h)/2, case_h_bottom/2])
                speaker_grille(speaker_grille_w, speaker_grille_h, wall + 1);
        }
        if (speaker_side == "left" || speaker_side == "both") {
            translate([-0.5, (case_d - speaker_grille_h)/2, case_h_bottom/2])
                speaker_grille(speaker_grille_w, speaker_grille_h, wall + 1);
        }

        // LED 灯带槽（底壳顶部边缘）
        if (led_enabled) {
            translate([wall, wall, case_h_bottom - led_strip_d])
                difference() {
                    rounded_box(case_w - wall*2, case_d - wall*2, led_strip_d + 1, case_r - 1);
                    translate([led_strip_w, led_strip_w, -0.5])
                        rounded_box(case_w - wall*2 - led_strip_w*2,
                                   case_d - wall*2 - led_strip_w*2,
                                   led_strip_d + 2, case_r - 2);
                }
        }
    }

    // 树莓派安装柱
    for (pos = pi_mount_positions()) {
        translate([pos[0], pos[1], wall])
            difference() {
                cylinder(h=5, r=3.2);
                cylinder(h=6, r=1.3);  // M2.5 螺丝孔
            }
    }

    // 卡扣柱（上下壳连接）
    for (pos = snap_positions()) {
        translate([pos[0], pos[1], case_h_bottom - 3])
            cylinder(h=3, r=2);
    }
}

// ============================================================
// 上壳
// ============================================================
module top_case() {
    difference() {
        union() {
            // 主体
            rounded_box(case_w, case_d, case_h_top, case_r);

            // 赛博朋克装饰线条（顶部凸起线）
            translate([10, 0, case_h_top - 1])
                cube([case_w - 20, 1.5, 1.5]);
            translate([10, case_d - 1.5, case_h_top - 1])
                cube([case_w - 20, 1.5, 1.5]);
        }

        // 挖空内部
        translate([wall, wall, -0.1])
            rounded_box(case_w - wall*2, case_d - wall*2, case_h_top - wall, case_r - 1);

        // --- 屏幕开窗 ---
        if (screen_enabled) {
            // 正面圆形窗口
            translate([case_w/2, -0.5, case_h_top/2 + screen_offset_y])
                rotate([-90, 0, 0])
                    cylinder(h=wall+1, d=screen_diameter);

            // 内侧稍大一点（放屏幕用）
            translate([case_w/2, wall - 1, case_h_top/2 + screen_offset_y])
                rotate([-90, 0, 0])
                    cylinder(h=3, d=screen_diameter + 3);
        }

        // --- 麦克风孔（顶部）---
        translate([case_w/2, case_d/3, case_h_top - wall - 0.5]) {
            cylinder(h=wall+1, d=3);
            // 周围小孔阵列
            for (a = [0:60:300]) {
                translate([5*cos(a), 5*sin(a), 0])
                    cylinder(h=wall+1, d=2);
            }
        }

        // --- 散热风扇安装位（顶部）---
        if (fan_mount) {
            translate([case_w/2 + 10, case_d/2 + 5, case_h_top - wall - 0.5]) {
                // 风扇主开孔（蜂窝状）
                for (row = [-2:2]) {
                    for (col = [-2:2]) {
                        offset_x = col * 5 + (row % 2) * 2.5;
                        offset_y = row * 4.3;
                        if (sqrt(offset_x*offset_x + offset_y*offset_y) < fan_size/2 - 2) {
                            translate([offset_x, offset_y, 0])
                                cylinder(h=wall+1, d=3.5);
                        }
                    }
                }
                // 风扇螺丝孔
                mount_r = fan_size/2 - 2;
                for (a = [45, 135, 225, 315]) {
                    translate([mount_r*cos(a)*0.7, mount_r*sin(a)*0.7, 0])
                        cylinder(h=wall+1, d=3);
                }
            }
        }

        // --- 顶部装饰通风槽（赛博朋克风格斜线）---
        for (i = [0:4]) {
            translate([15 + i*8, case_d - wall - 0.5, case_h_top - 12])
                cube([3, wall+1, 8]);
        }

        // --- 上壳卡扣孔 ---
        for (pos = snap_positions()) {
            translate([pos[0], pos[1], -0.1])
                cylinder(h=4, r=2.2);
        }
    }

    // LED 灯带导光条位置标记（内壁）
    if (led_enabled) {
        translate([case_w/2, -0.1, case_h_top - 8])
            rotate([-90, 0, 0])
                linear_extrude(0.8)
                    text("LED", size=4, halign="center", font="Liberation Mono:style=Bold");
    }

    // 内壁 "PROJECT KEI" 文字
    translate([case_w/2, case_d - wall + 0.1, case_h_top/2])
        rotate([90, 0, 0])
            linear_extrude(0.8)
                text("PROJECT KEI", size=4, halign="center", font="Liberation Mono:style=Bold");
}

// ============================================================
// 辅助模块
// ============================================================

// 圆角矩形盒子
module rounded_box(w, d, h, r) {
    hull() {
        for (x = [r, w-r]) {
            for (y = [r, d-r]) {
                translate([x, y, 0])
                    cylinder(h=h, r=r);
            }
        }
    }
}

// 扬声器格栅（横条纹）
module speaker_grille(w, h, depth) {
    slot_h = 1.5;
    gap = 2.5;
    n_slots = floor(h / (slot_h + gap));

    for (i = [0:n_slots-1]) {
        translate([0, i * (slot_h + gap), -w/2])
            cube([depth, slot_h, w]);
    }
}

// 树莓派安装孔位置
function pi_mount_positions() = [
    [wall + clearance + pi_mount_inset_x,
     wall + clearance + pi_mount_inset_y],
    [wall + clearance + pi_mount_inset_x + pi_mount_dx,
     wall + clearance + pi_mount_inset_y],
    [wall + clearance + pi_mount_inset_x,
     wall + clearance + pi_mount_inset_y + pi_mount_dy],
    [wall + clearance + pi_mount_inset_x + pi_mount_dx,
     wall + clearance + pi_mount_inset_y + pi_mount_dy],
];

// 卡扣位置
function snap_positions() = [
    [wall + 5, case_d/2],
    [case_w - wall - 5, case_d/2],
    [case_w/2, wall + 5],
    [case_w/2, case_d - wall - 5],
];

// 四角位置
function corner_positions(w, d) = [
    [(case_w - w)/2, (case_d - d)/2],
    [(case_w + w)/2, (case_d - d)/2],
    [(case_w - w)/2, (case_d + d)/2],
    [(case_w + w)/2, (case_d + d)/2],
];
