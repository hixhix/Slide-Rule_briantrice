#!/usr/bin/env python3

"""
Slide Rule Scale Generator 2.0 by Javier Lopez 2020
v3.0 Brian T. Rice <briantrice@gmail.com> 2024
Available Scales: A B C D K R1 R2 CI DI CF DF CIF L S T ST

Table of Contents
   1. Setup
   2. Fundamental Functions
   3. Scale Generating Function
   4. Line Drawing Functions
   5. Stickers
   6. Models
   7. Commands
"""

# ----------------------1. Setup----------------------------

import inspect
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from enum import Enum
from functools import cache
from itertools import chain

from PIL import Image, ImageFont, ImageDraw


def keys_of(obj: object):
    return [k for k, _ in inspect.getmembers(obj) if not k.startswith('__')]


# Angular constants:
TAU = math.tau
PI = math.pi
PI_HALF = PI / 2
DEG_FULL = 360
DEG_SEMI = DEG_FULL // 2
DEG_RT = DEG_SEMI // 2

BYTE_MAX = 255


class Colors(Enum):
    WHITE = (BYTE_MAX, BYTE_MAX, BYTE_MAX)
    RED = (BYTE_MAX, 0, 0)
    GREEN = (0, BYTE_MAX, 0)
    BLUE = (0, 0, BYTE_MAX)
    BLACK = (0, 0, 0)

    CUT = BLUE  # color which indicates CUT
    CUTOFF = (230, 230, 230)
    CUTOFF2 = (234, 36, 98)
    SYM_GREEN = (34, 139, 30)  # Override PIL for green for slide rule symbol conventions
    FC_LIGHT_BLUE_BG = (194, 235, 247)  # Faber-Castell scale background
    FC_LIGHT_GREEN_BG = (203, 243, 225)  # Faber-Castell scale background
    PICKETT_EYE_SAVER_YELLOW = (253, 253, 150)  # pastel yellow
    LIGHT_BLUE = 'lightblue'

    RED_WHITE_1 = (BYTE_MAX, 224, 224)
    RED_WHITE_2 = (BYTE_MAX, 192, 192)
    RED_WHITE_3 = (BYTE_MAX, 160, 160)


@cache
def pil_color(col_spec):
    return col_spec.value if isinstance(col_spec, Colors) else col_spec


class FontSize(Enum):
    TITLE = 140
    SUBTITLE = 120
    SC_LBL = 90
    N_XL = 75
    N_LG = 60
    N_MD = 55
    N_SM = 45
    N_XS = 35


class FontStyle(Enum):
    REG = 0  # regular
    ITALIC = 1  # italic
    BOLD = 2  # bold
    BOLD_ITALIC = 3  # bold italic


class Font:
    """Fonts are families per https://cm-unicode.sourceforge.io/font_table.html"""
    Family = tuple[str, str, str, str]
    CMUTypewriter: Family = ('cmuntt.ttf', 'cmunit.ttf', 'cmuntb.ttf', 'cmuntx.ttf')
    # = CMUTypewriter-Regular, CMUTypewriter-Italic, CMUTypewriter-Bold, CMUTypewriter-BoldItalic
    CMUSansSerif: Family = ('cmunss.ttf', 'cmunsi.ttf', 'cmunsx.ttf', 'cmunso.ttf')
    # = CMUSansSerif, CMUSansSerif-Oblique, CMUSansSerif-Bold, CMUSansSerif-BoldOblique
    CMUConcrete: Family = ('cmunorm.ttf', 'cmunoti.ttf', 'cmunobx.ttf', 'cmunobi.ttf')
    # = CMUConcrete-Roman, CMUConcrete-Italic, CMUConcrete-Bold, CMUConcrete-BoldItalic
    CMUBright: Family = ('cmunbsr.ttf', 'cmunbso.ttf', 'cmunbsr.ttf', 'cmunbso.ttf')
    # = CMUBright-SemiBold, CMUBright-SemiBoldOblique, CMUBright-SemiBold, CMUBright-SemiBoldOblique
    # 'cmunbmr.ttf', 'cmunbmo.ttf',  # CMUBright-Roman, CMUBright-Oblique

    @classmethod
    @cache
    def get_font(cls, font_family: Family, fs: int, font_style: int):
        font_name = font_family[font_style]
        return ImageFont.truetype(font_name, fs)

    @classmethod
    def font_for(cls, font_family: Family, font_size, font_style=FontStyle.REG, h_ratio: float = None):
        fs: int = font_size.value if isinstance(font_size, FontSize) else font_size
        if h_ratio and h_ratio != 1:
            fs = round(fs * h_ratio)
        return cls.get_font(font_family, fs, font_style.value)


@dataclass(frozen=True)
class Style:
    fg: Colors = Colors.BLACK
    """foreground color black"""
    bg: Colors = Colors.WHITE
    """background color white"""
    decreasing_color: Colors = Colors.RED
    """color for a decreasing value scale"""
    decimal_color: Colors = Colors.BLACK
    """color for sub-decimal points"""
    bg_colors: dict = field(default_factory=dict)
    """background color overrides for particular scale keys"""
    font_family: Font.Family = Font.CMUTypewriter
    overrides: dict[str, dict[str, object]] = field(default_factory=dict)

    def fg_col(self, element: str, is_increasing=True):
        return self.override_for(element, 'color',
                                 self.fg if is_increasing else self.decreasing_color)

    def bg_col(self, element: str):
        return self.bg_colors.get(element)

    def overrides_for(self, element: str) -> dict:
        return self.overrides.get(element)

    def override_for(self, element: str, key: str, default):
        sc_overrides = self.overrides_for(element)
        return sc_overrides.get(key, default) if sc_overrides else default

    def numeral_decimal_color(self):
        return self.decimal_color

    def font_for(self, font_size, font_style=FontStyle.REG, h_ratio=None):
        return Font.font_for(self.font_family, font_size, font_style, h_ratio)

    @staticmethod
    def sym_dims(symbol: str, font: ImageFont) -> tuple[int, int]:
        """Gets the size dimensions (width, height) of the input text"""
        (x1, y1, x2, y2) = font.getbbox(symbol)
        return x2 - x1, y2 - y1 + 20

    @classmethod
    def sym_width(cls, symbol: str, font: ImageFont) -> int:
        (x1, _, x2, _) = font.getbbox(symbol)
        return x2 - x1


class Styles:
    Default = Style()
    PickettEyeSaver = Style(
        font_family=Font.CMUBright,
        bg=Colors.PICKETT_EYE_SAVER_YELLOW
    )
    Graphoplex = Style(
        font_family=Font.CMUBright,
        decimal_color=Colors.LIGHT_BLUE
    )


class HMod(Enum):
    """Tick height size factors (h_mod in pat)"""
    DOT = 0.25
    XS = 0.5
    SM = 0.85
    MED = 1
    LG = 1.15
    LG2 = 1.2
    XL = 1.3


class Side(Enum):
    """Side of the slide (front or rear)"""
    FRONT = 'front'
    REAR = 'rear'


class RulePart(Enum):
    STATOR_TOP = 'stator_top'
    SLIDE = 'slide'
    STATOR_BOTTOM = 'stator_bottom'


class Geometry:
    """Slide Rule Geometric Parameters"""
    oX: int = 100  # x margins
    oY: int = 100  # y margins
    side_w: int = 8000  # 30cm = 11.8in
    side_h: int = 1600  # 6cm = 2.36in
    slide_h: int = 640  # 2.4cm = 0.945in

    SH: int = 160  # 6mm
    """scale height"""
    SL: int = 5600  # 21cm = 8.27in
    """scale length"""
    DEFAULT_SCALE_WH = (SL, SH)
    SM: int = 0
    """Scale margin"""

    # Ticks, Labels, are referenced from li as to be consistent
    STH: int = 70  # 2.62mm
    """standard tick height"""
    STT: int = 3  # 0.1125mm
    """standard tick thickness"""
    PixelsPerCM = 1600 / 6
    PixelsPerIN = PixelsPerCM * 2.54

    NO_MARGINS = (0, 0)
    DEFAULT_TICK_WH = (STT, STH)

    top_margin = 110
    scale_h_overrides: dict[Side, dict[str, int]] = {Side.FRONT: {}, Side.REAR: {}}
    margin_overrides: dict[Side, dict[str, int]] = {Side.FRONT: {}, Side.REAR: {}}

    def __init__(self, side_wh: (int, int), margins_xy: (int, int), scale_wh: (int, int), tick_wh: (int, int),
                 slide_h: int, top_margin: int = None,
                 scale_h_overrides: dict[Side, dict[int: [str]]] = None,
                 margin_overrides: dict[Side, dict[int: [str]]] = None):
        (self.side_w, self.side_h) = side_wh
        (self.oX, self.oY) = margins_xy
        (self.SL, self.SH) = scale_wh
        (self.STT, self.STH) = tick_wh
        self.tick_mid_offset = self.STT // 2 + 1
        self.slide_h = slide_h
        if top_margin:
            self.top_margin = top_margin
        self.scale_h_overrides = {Side.FRONT: {}, Side.REAR: {}}
        if scale_h_overrides:
            for side in Side:
                side_overrides = scale_h_overrides.get(side, {})
                for h, sc_keys in side_overrides.items():
                    for sc_key in sc_keys:
                        self.scale_h_overrides[side][sc_key] = h
        self.margin_overrides = {Side.FRONT: {}, Side.REAR: {}}
        if margin_overrides:
            for side in Side:
                side_overrides = margin_overrides.get(side, {})
                for h, sc_keys in side_overrides.items():
                    for sc_key in sc_keys:
                        self.margin_overrides[side][sc_key] = h

    @property
    def total_w(self):
        return self.side_w + 2 * self.oX

    @property
    def midpoint_x(self):
        return self.total_w // 2

    @property
    def print_height(self):
        return self.side_h * 2 + 3 * self.oY

    @property
    def stator_h(self):
        return (self.side_h - self.slide_h) // 2

    @property
    def cutoff_w(self):
        """Default cutoff width ensures a square anchor piece."""
        return self.stator_h

    @property
    def li(self):
        """left index offset from left edge"""
        return (self.total_w - self.SL) // 2

    @property
    def min_tick_offset(self):
        """minimum tick horizontal offset"""
        return self.STT * 3  # separate each tick by at least the space of its width

    def tick_h(self, h_mod: HMod = None, h_ratio=None) -> int:
        result = self.STH
        if h_mod:
            result *= h_mod.value
        if h_ratio and h_ratio != 1:
            result *= h_ratio
        return round(result)

    def edge_h(self, part: RulePart, top):
        if part == RulePart.STATOR_TOP:
            return 0 if top else self.stator_h
        if part == RulePart.SLIDE:
            return self.stator_h + (0 if top else self.slide_h)
        if part == RulePart.STATOR_BOTTOM:
            return self.stator_h + self.slide_h if top else self.side_h
        return 0

    def scale_h(self, sc, side: Side = None, default: int = None) -> int:
        key = sc.key
        if side:
            return self.scale_h_overrides[side].get(key, default or self.SH)
        return self.scale_h_overrides[Side.FRONT].get(
            key, self.scale_h_overrides[Side.REAR].get(key, default or self.SH))

    def scale_margin(self, sc, side: Side = None, default=SM) -> int:
        key = sc.key
        if side:
            return self.margin_overrides[side].get(key, default or self.SM)
        return self.margin_overrides[Side.FRONT].get(
            key, self.margin_overrides[Side.REAR].get(key, default or self.SM)
        )

    def scale_h_ratio(self, sc, side=None):
        scale_h = self.scale_h(sc, side=side)
        default_scale_h = self.DEFAULT_SCALE_WH[1]
        return scale_h / default_scale_h if scale_h != default_scale_h else None

    def cutoff_outline(self, y_off):
        """
        Creates and returns the left cutoff piece outline in vectors as: (x1,x2,y1,y2)

        ~Cute~little~visualization~

        x_left x_mid x_right
        0  ↓    ↓    ↓
        ↓         1↓   ← 0
                ┌────┐ ← y_top
                │    │
                │    │
             4→ │    │ ←6
                │    │
                │    │
             2↓ │    │
           ┌────┘    │ ← y_mid
        5→ │         │
           │         │
           └─────────┘ ← y_bottom
               3↑      ← side_h
        """
        side_h = self.side_h
        cutoff_w = self.cutoff_w
        b = 30  # offset of metal from boundary
        x_left = b + self.oX
        x_mid = x_left + cutoff_w // 2
        x_right = cutoff_w - b + self.oX
        y_top = b + y_off
        y_mid = y_top + side_h - self.stator_h
        y_bottom = side_h - b + y_off
        return [(x_mid, x_right, y_top, y_top),  # 1
                (x_left, x_mid, y_mid, y_mid),  # 2
                (x_left, x_right, y_bottom, y_bottom),  # 3
                (x_mid, x_mid, y_top, y_mid),  # 4
                (x_left, x_left, y_mid, y_bottom),  # 5
                (x_right, x_right, y_top, y_bottom)]  # 6

    def mirror_vectors_h(self, vectors: list[tuple[int, int, int, int]]):
        """(x1, x2, y1, y2) mirrored across the centerline"""
        total_w = self.total_w
        return [(total_w - x2, total_w - x1, y1, y2) for (x1, x2, y1, y2) in vectors]

    @staticmethod
    def mirror_vectors_v(vectors: list[tuple[int, int, int, int]], mid_y):
        """(x1, x2, y1, y2) mirrored across a horizontal line"""
        return [(x1, x2, mid_y - y2, mid_y - y1) for (x1, x2, y1, y2) in vectors]


class Align(Enum):
    """Scale Alignment (ticks and labels against upper or lower bounds)"""
    UPPER = 'upper'  # Upper alignment
    LOWER = 'lower'  # Lower Alignment


TEN = 10
HUNDRED = TEN * TEN


@dataclass(frozen=True)
class GaugeMark:
    sym: str
    value: float = None
    comment: str = None


class Marks:
    e = GaugeMark('e', math.e, comment='base of natural logarithms')
    inv_e = GaugeMark('1/e', 1 / math.e, comment='base of natural logarithms')
    tau = GaugeMark('τ', TAU, comment='ratio of circle circumference to radius')
    pi = GaugeMark('π', PI, comment='ratio of circle circumference to diameter')
    pi_half = GaugeMark('π/2', PI_HALF, comment='ratio of quarter arc length to radius')
    inv_pi = GaugeMark('M', 1 / PI, comment='reciprocal of π')

    deg_per_rad = GaugeMark('r', DEG_FULL / TAU / TEN, comment='degrees per radian')
    rad_per_deg = GaugeMark('ρ', TAU / DEG_FULL, comment='radians per degree')
    rad_per_min = GaugeMark('ρ′', TAU / DEG_FULL * 60, comment='radians per minute')
    rad_per_sec = GaugeMark('ρ″', TAU / DEG_FULL * 60 * 60, comment='radians per second')

    ln_over_log10 = GaugeMark('L', 1 / math.log10(math.e), comment='ratio of natural log to log base 10')

    sqrt_ten = GaugeMark('√10', math.sqrt(TEN), comment='square root of 10')
    cube_root_ten = GaugeMark('c', math.pow(TEN, 1 / 3), comment='cube root of 10')


class ConversionMarks:
    cm_per_in = GaugeMark('in', 2.54, comment='cm per in')
    sq_cm_per_in = GaugeMark('sq in', cm_per_in.value**2, comment='cm² per in²')
    cu_cm_per_in = GaugeMark('cu in', cm_per_in.value**3, comment='cm³ per in³')
    ft_per_m = GaugeMark('ft', HUNDRED/(cm_per_in.value*12), comment='ft per m')
    yd_per_m = GaugeMark('yd', 3/ft_per_m.value, comment='yd per m')
    km_per_mi = GaugeMark('mi', cm_per_in.value*12*5280/1000, comment='mi per km')
    qt_per_l = GaugeMark('qt', 0.9463525, comment='US qt per l')
    gal_per_l = GaugeMark('gal', qt_per_l.value*4, 'US gal per l')
    lb_per_kg = GaugeMark('lb', 2.2046, comment='lbs per kg')
    hp_per_kw = GaugeMark('N', 1.341022, comment='mechanical horsepower per kW')
    g = GaugeMark('g', 9.80665, comment='gravity acceleration on Earth in m/s²')


# ----------------------2. Fundamental Functions----------------------------


TickFactors = tuple[int, int, int]
TF_BY_MIN: dict[int, TickFactors] = {  # Best tick subdivision pattern for a given minimum overall division
    500: (10, 10, 5),
    250: (10, 5, 5),
    100: (10, 2, 5),
    50: (2, 5, 5),
    25: (1, 5, 5),
    20: (2, 5, 2),
    10: (2, 5, 1),
    5: (1, 5, 1),
    2: (1, 2, 1),
    1: (1, 1, 1)
}
TF_MIN = sorted(TF_BY_MIN.keys(), reverse=True)
TF_BIN: TickFactors = (4, 4, 4)


def t_s(s1: int, f: TickFactors):
    """tick iterative subdivision"""
    s2 = s1 if f[0] == 1 else s1 // f[0]
    s3 = s2 if f[1] == 1 else s2 // f[1]
    s4 = s3 if f[2] == 1 else s3 // f[2]
    return s1, s2, s3, s4


DEBUG = False
DRAW_RADICALS = True


@dataclass(frozen=True)
class Renderer:
    r: ImageDraw.ImageDraw = None
    geometry: Geometry = None
    style: Style = None

    @classmethod
    def make(cls, i: Image.Image, g: Geometry, s: Style):
        return cls(ImageDraw.Draw(i), g, s)

    def draw_box(self, x0, y0, dx, dy, col, width=1):
        self.r.rectangle((x0, y0, x0 + dx, y0 + dy), outline=pil_color(col), width=width)

    def fill_rect(self, x0, y0, dx, dy, col):
        self.r.rectangle((x0, y0, x0 + dx, y0 + dy), fill=pil_color(col))

    def draw_circle(self, xc, yc, r, col):
        self.r.ellipse((xc - r, yc - r, xc + r, yc + r), outline=pil_color(col))

    def draw_tick(self, y_off: int, x: int, height: int, col, scale_h: int, al: Align):
        """Places an individual tick, aligned to top or bottom of scale"""
        x0 = x + self.geometry.li - 2
        y0 = y_off
        if al == Align.LOWER:
            y0 += scale_h - height
        self.fill_rect(x0, y0, self.geometry.STT, height, col)

    def pat(self, y_off: int, sc, al: Align,
            i_start, i_end, i_sf, steps_i, steps_th, steps_font, digit1):
        """
        Place ticks in a graduated pattern. All options are given, not inferred.
        4 levels of tick steps and sizes needed, and three optional fonts for numerals.
        :param y_off: y pos
        :param Scale sc:
        :param Align al: alignment
        :param int i_start: index across the scale to start at
        :param int i_end: index across the scale to end at
        :param int i_sf: scale factor - how much to divide the inputs by before scaling (to generate fine decimals)
        :param tuple[int, int, int, int] steps_i: patterning steps, large to small
        :param tuple[int, int, int, int] steps_th: tick sizes, large to small, per step
        :param tuple[FreeTypeFont, FreeTypeFont, FreeTypeFont] steps_font: optional font sizes, for numerals above ticks
        :param tuple[bool, bool, bool]|bool digit1: whether to show the numerals as the most relevant digit only
        """
        step1, step2, step3, step4 = steps_i
        th1, th2, th3, th4 = steps_th
        font1, font2, font3 = steps_font
        scale_w = self.geometry.SL
        scale_h = self.geometry.scale_h(sc)
        sym_col = self.style.fg_col(sc.key, is_increasing=sc.is_increasing)
        tenth_col = self.style.decimal_color if sc.is_increasing else sym_col
        if isinstance(digit1, bool):
            digit1 = [digit1, False, False]
        for i in range(i_start, i_end, step4):
            n = i / i_sf
            x = sc.scale_to(n, scale_w)
            tick_h = th4
            if i % step1 == 0:
                tick_h = th1
                if font1:
                    self.draw_numeral(sig_digit_of(n) if digit1[0] else n, y_off, sym_col, scale_h, x, th1, font1, al)
            elif i % step2 == 0:
                tick_h = th2
                if font2:
                    self.draw_numeral(sig_digit_of(n) if digit1[1] else n, y_off, sym_col, scale_h, x, th2, font2, al)
            elif i % step3 == 0:
                tick_h = th3
                if font3:
                    self.draw_numeral(sig_digit_of(n) if digit1[2] else n, y_off, tenth_col, scale_h, x, th3, font3, al)
            self.draw_tick(y_off, x, tick_h, sym_col, scale_h, al)

    def pat_auto(self, y_off, sc, al, x_start=None, x_end=None, include_last=False):
        """
        Draw a graduated pattern of tick marks across the scale range, by algorithmic selection.
        From some tick patterns in order and by generic suitability, pick the most detailed with a sufficient tick gap.
        """
        if not x_start:
            x_start = sc.value_at_start()
        if not x_end:
            x_end = sc.value_at_end()
        if x_start > x_end:
            x_start, x_end = x_end, x_start
        g = self.geometry
        min_tick_offset = g.min_tick_offset
        log_diff = abs(math.log10(abs((x_end - x_start) / max(x_start, x_end))))
        num_digits = math.ceil(log_diff) + 3
        scale_w = g.SL
        sf = 10 ** num_digits  # ensure enough precision for int ranges
        # Ensure a reasonable visual density of numerals
        frac_w = sc.offset_between(x_start, x_end, 1)
        step_num = 10 ** max(int(math.log10(x_end - x_start) - 0.5 * frac_w) + num_digits, 0)
        sub_div4 = next((TF_BY_MIN[i] for i in TF_MIN if i <= step_num
                         and sc.min_offset_for_delta(x_start, x_end, step_num / i / sf, scale_w) >= min_tick_offset),
                        TF_BY_MIN[1])
        (_, step2, step3, step4) = t_s(step_num, sub_div4)
        # Iteration Setup
        i_start = int(x_start * sf)
        i_offset = i_start % step4
        if i_offset > 0:  # Align to first tick on or after start
            i_start = i_start - i_offset + step4
        # Determine numeral font size
        scale_hf = g.scale_h_ratio(sc)
        s = self.style
        num_font = s.font_for(FontSize.N_LG, h_ratio=scale_hf)
        numeral_tick_offset = sc.min_offset_for_delta(x_start, x_end, step_num / sf, scale_w)
        max_num_chars = numeral_tick_offset // s.sym_width('_', num_font)
        if max_num_chars < 2:
            num_font = s.font_for(FontSize.N_SM, h_ratio=scale_hf)
        # If there are sub-digit ticks to draw, and enough space for single-digit numerals:
        sub_num = (step4 < step3 < step_num) and max_num_chars > 8
        # Tick Heights:
        dot_th = g.tick_h(HMod.DOT, scale_hf)
        self.pat(y_off, sc, al,
                 i_start, int(x_end * sf + (1 if include_last else 0)), sf,
                 (step_num, step2, step3, step4),
                 (
                     g.tick_h(HMod.MED, scale_hf),
                     g.tick_h(HMod.XL if step3 == step_num // 2 and step4 < step3 else HMod.XS, scale_hf),
                     g.tick_h(HMod.XS, scale_hf) if step4 < step3 else dot_th,
                     dot_th),
                 (num_font,
                  s.font_for(FontSize.N_SM, h_ratio=scale_hf) if sub_num and step2 == step_num // 10 or step2 == step_num // 2 else None,
                  s.font_for(FontSize.N_XS, h_ratio=scale_hf) if sub_num and step3 == step_num // 10 else None),
                 (max_num_chars < 3, max_num_chars < 16, max_num_chars < 128))

    def draw_symbol(self, symbol: str, color, x_left: float, y_top: float, font: ImageFont):
        color = pil_color(color)
        if '∡' in symbol:
            symbol = symbol.replace('∡', '')
        if '⅓' in symbol:
            symbol = symbol.replace('⅓', '')
        if DEBUG:
            w, h = self.style.sym_dims(symbol, font)
            self.draw_box(x_left, y_top, w, h, 'grey')
        self.r.text((x_left, y_top), symbol, font=font, fill=color)
        if DRAW_RADICALS:
            radicals = re.search(r'[√∛∜]', symbol)
            if radicals:
                w, h = self.style.sym_dims(symbol, font)
                n_ch = radicals.start() + 1
                (w_ch, h_rad) = self.style.sym_dims('√', font)
                (_, h_num) = self.style.sym_dims('1', font)
                line_w = h_rad // 14
                y_bar = y_top + max(10, round(h - h_num - line_w * 2))
                self.r.line((x_left + w_ch * n_ch - w_ch // 10, y_bar, x_left + w, y_bar), width=line_w, fill=color)

    def draw_sym_al(self, symbol, y_off, color, al_h, x, y, font, al):
        """
        :param str|Colors color: color that PIL recognizes
        :param int y_off: y pos
        :param int al_h: height for alignment
        :param str symbol: content (text or number)
        :param x: offset of centerline from left index (li)
        :param y: offset of base from baseline (LOWER) or top from upper line (UPPER)
        :param FreeTypeFont font:
        :param Align al: alignment
        """

        if not symbol:
            return
        (base_sym, exponent, subscript) = symbol_parts(symbol)
        w, h = Style.sym_dims(base_sym, font)

        y_top = y_off
        if al == Align.UPPER:
            y_top += y
        elif al == Align.LOWER:
            y_top += al_h - 1 - y - h * 1.2
        x_left = x + self.geometry.li - w / 2 + self.geometry.STT / 2
        self.draw_symbol(base_sym, color, round(x_left), y_top, font)

        if exponent or subscript:
            sub_font_size = FontSize.N_LG if font.size == FontSize.SC_LBL else font.size
            sub_font = self.style.font_for(sub_font_size, h_ratio=0.75)
            x_right = round(x_left + w)
            if exponent:
                self.draw_symbol_sup(exponent, color, h, x_right, y_top, sub_font)
            if subscript:
                self.draw_symbol_sub(subscript, color, h, x_right, y_top, sub_font)

    def draw_numeral(self, num, y_off, color, scale_h, x, y, font, al):
        """Draw a numeric symbol for a scale"""
        if isinstance(num, int):
            num_sym = str(num)
        elif not num.is_integer():
            num_sym = str(num)
            if num_sym.startswith('0.'):
                expon = math.log10(num)
                if expon.is_integer() and abs(expon) > 2:
                    num_sym = f'10^{int(expon)}'
                else:
                    num_sym = num_sym[1:]  # Omit leading zero digit
        elif num == 0:
            num_sym = '0'
        else:
            expon = math.log10(num)
            if expon.is_integer() and abs(expon) > 2:
                num_sym = f'10^{int(expon)}'
            else:
                num_sym = str(int(num))

        self.draw_sym_al(num_sym, y_off, color, scale_h, x, y, font, al)

    def draw_symbol_sup(self, sup_sym, color, h_base, x_left, y_base, font):
        if len(sup_sym) == 1 and unicodedata.category(sup_sym) == 'No':
            sup_sym = str(unicodedata.digit(sup_sym))
        self.draw_symbol(sup_sym, color, x_left, y_base - (0 if sup_sym in PRIMES else h_base / 2), font)

    def draw_symbol_sub(self, sub_sym, color, h_base, x_left, y_base, font):
        self.draw_symbol(sub_sym, color, x_left, y_base + h_base / 2, font)

    def draw_mark(self, mark: GaugeMark, y_off: int, sc, font, al, col=None, shift_adj=0, side=None):
        if not col:
            col = self.style.fg_col(sc.key, is_increasing=sc.is_increasing)
        g = self.geometry
        x = sc.scale_to(mark.value, g.SL, shift_adj=shift_adj)
        scale_h = g.scale_h(sc, side=side)
        tick_h = g.tick_h(HMod.MED, h_ratio=g.scale_h_ratio(sc, side=side))
        self.draw_tick(y_off, x, tick_h, col, scale_h, al)
        self.draw_sym_al(mark.sym, y_off, col, scale_h, x, tick_h, font, al)

    # ----------------------4. Line Drawing Functions----------------------------

    def draw_borders(self, y0: int, side: Side, color=Colors.BLACK.value):
        """Place initial borders around scales"""
        # Main Frame
        total_w = self.geometry.total_w
        side_w = self.geometry.side_w
        side_h = self.geometry.side_h
        stator_h = self.geometry.stator_h
        y_offsets = [0, stator_h - 1, side_h - stator_h - 1, side_h - 2]
        o_x = self.geometry.oX
        for horizontal_y in [y0 + y_off for y_off in y_offsets]:
            self.fill_rect(o_x, horizontal_y, side_w, 1, color)
        for vertical_x in [o_x, total_w - o_x]:
            self.fill_rect(vertical_x, y0, 1, side_h, color)

        # Top Stator Cut-outs
        # if side == SlideSide.FRONT:
        y_start = y0
        if side == Side.REAR:
            y_start += side_h - stator_h
        half_stock_height = stator_h // 2
        for horizontal_x in [half_stock_height + o_x, (total_w - half_stock_height) - o_x]:
            self.fill_rect(horizontal_x, y_start, 1, stator_h, color)

    def draw_metal_cutoffs(self, y_off: int, side: Side):
        """Draw the metal bracket locations for viewing"""
        # Initial Boundary verticals
        g = self.geometry
        verticals = [g.cutoff_w + g.oX, g.total_w - g.cutoff_w - g.oX]
        for i, start in enumerate(verticals):
            self.fill_rect(start - 1, y_off, 2, i, Colors.CUTOFF)

        cutoff_fl = g.cutoff_outline(y_off)

        # Symmetrically create the right piece
        coords = cutoff_fl + g.mirror_vectors_h(cutoff_fl)

        # If backside, first apply a vertical reflection
        if side == Side.REAR:
            mid_y = 2 * y_off + g.side_h
            coords = g.mirror_vectors_v(coords, mid_y)
        for (x1, x2, y1, y2) in coords:
            self.r.rectangle((x1 - 1, y1 - 1, x2 + 1, y2 + 1), fill=Colors.CUTOFF2.value)

    # ---------------------- 5. Stickers -----------------------------

    def draw_corners(self, x1, y1, x2, y2, arm_w=20):
        """
        :param int x1: First corner of box
        :param int y1: First corner of box
        :param int x2: Second corner of box
        :param int y2: Second corner of box
        :param int arm_w: width of extension cross arms
        """
        col = pil_color(Colors.CUT)
        # horizontal cross arms at 4 corners:
        self.r.line((x1 - arm_w, y1, x1 + arm_w, y1), col)
        self.r.line((x1 - arm_w, y2, x1 + arm_w, y2), col)
        self.r.line((x2 - arm_w, y1, x2 + arm_w, y1), col)
        self.r.line((x2 - arm_w, y2, x2 + arm_w, y2), col)
        # vertical cross arms at 4 corners:
        self.r.line((x1, y1 - arm_w, x1, y1 + arm_w), col)
        self.r.line((x1, y2 - arm_w, x1, y2 + arm_w), col)
        self.r.line((x2, y1 - arm_w, x2, y1 + arm_w), col)
        self.r.line((x2, y2 - arm_w, x2, y2 + arm_w), col)


RE_EXPON_CARET = re.compile(r'^(.+)\^([-0-9.A-Za-z]+)$')
RE_SUB_UNDERSCORE = re.compile(r'^(.+)_([-0-9.A-Za-z]+)$')
RE_EXPON_UNICODE = re.compile(r'^([^⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)([⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)$')
RE_SUB_UNICODE = re.compile(r'^([^₀₁₂₃]+)([₀₁₂₃]+)$')


def num_char_convert(char):
    if char == '⁻':
        return '-'
    return unicodedata.digit(char)


def unicode_sub_convert(symbol: str):
    return ''.join(map(str, map(num_char_convert, symbol)))


def split_symbol_by(symbol: str, text_re: re.Pattern, unicode_re: re.Pattern):
    base_sym = symbol
    subpart_sym = None
    matches = re.match(text_re, symbol)
    if matches:
        base_sym = matches.group(1)
        subpart_sym = matches.group(2)
    else:
        matches = re.match(unicode_re, symbol)
        if matches:
            base_sym = matches.group(1)
            subpart_sym = unicode_sub_convert(matches.group(2))
    return base_sym, subpart_sym


PRIMES = "'ʹʺ′″‴"


def symbol_with_expon(symbol: str):
    if len(symbol) > 1 and symbol[-1] in PRIMES:
        return symbol[:-1], symbol[-1:]
    return split_symbol_by(symbol, RE_EXPON_CARET, RE_EXPON_UNICODE)


def symbol_with_subscript(symbol: str):
    return split_symbol_by(symbol, RE_SUB_UNDERSCORE, RE_SUB_UNICODE)


def symbol_parts(symbol: str):
    (base_sym, subscript) = symbol_with_subscript(symbol)
    (base_sym, expon) = symbol_with_expon(base_sym)
    return base_sym, expon, subscript


class BleedDir(Enum):
    UP = 'up'
    DOWN = 'down'


def extend(image: Image, geom: Geometry, y: int, direction: BleedDir, amplitude: int):
    """
    Used to create bleed for sticker cutouts
    y: pixel row to duplicate
    amplitude: number of pixels to extend
    """
    w = geom.total_w
    for x in range(0, w):
        bleed_color = image.getpixel((x, y))
        for yi in range(y - amplitude, y) if direction == BleedDir.UP else range(y, y + amplitude):
            image.putpixel((x, yi), bleed_color)


# ----------------------3. Scale Generating Function----------------------------


LOG_TEN = math.log(TEN)
LOG_ZERO = -math.inf
ε = 1e-20


def unit(x): return x
def gen_base(x): return math.log10(x)
def pos_base(p): return math.pow(TEN, p)


def scale_sin_tan_radians(x):
    return gen_base(HUNDRED * (math.sin(x) + math.tan(x)) / 2)


def angle_opp(x):
    """The opposite angle in degrees across a right triangle."""
    return DEG_RT - x


def clamp(x, min_value, max_value):
    return max(min(x, max_value), min_value)


@dataclass(frozen=True)
class ScaleFN:
    """Encapsulates a generating function and its inverse.
    The generating function takes X and returns the fractional position in the unit output space it should locate.
    The inverse function takes a fraction of a unit output space, returning the value to indicate at that position.

    These should be monotonic over their intended range.
    """
    fn: callable
    inverse: callable
    is_increasing: bool = True
    min_x: float = -math.inf
    max_x: float = math.inf

    def __call__(self, x):
        return self.fn(x)

    def clamp_input(self, x):
        return clamp(x, self.min_x, self.max_x)

    def inverted(self):
        return ScaleFN(self.inverse, self.fn, not self.is_increasing)

    def position_of(self, value):
        return self.fn(value)

    def value_at(self, position):
        return self.inverse(position)

    def value_at_start(self):
        return self.value_at(0)

    def value_at_end(self):
        return self.value_at(1)


class ScaleFNs:
    Unit = ScaleFN(unit, unit)
    F_to_C = ScaleFN(lambda f: (f - 32) * 5 / 9, lambda c: (c * 9 / 5) + 32)
    neper_to_db = ScaleFN(lambda x_db: x_db / (20 / math.log(TEN)), lambda x_n: x_n * 20 / math.log(TEN))

    Base = ScaleFN(gen_base, pos_base, min_x=ε)
    Square = ScaleFN(lambda x: gen_base(x) / 2, lambda p: pos_base(p * 2))
    Cube = ScaleFN(lambda x: gen_base(x) / 3, lambda p: pos_base(p * 3))
    Inverse = ScaleFN(lambda x: 1 - gen_base(x), lambda p: pos_base(1 - p), is_increasing=False, min_x=ε)
    InverseSquare = ScaleFN(lambda x: 1 - gen_base(x) / 2, lambda p: pos_base(1 - p * 2), is_increasing=False, min_x=ε)
    SquareRoot = ScaleFN(lambda x: gen_base(x) * 2, lambda p: pos_base(p / 2), min_x=ε)
    CubeRoot = ScaleFN(lambda x: gen_base(x) * 3, lambda p: pos_base(p / 3), min_x=ε)
    Log10 = ScaleFN(lambda x: x / TEN, lambda p: p * TEN, min_x=ε)
    Ln = ScaleFN(lambda x: x / LOG_TEN, lambda p: p * LOG_TEN, min_x=ε)
    Sin = ScaleFN(lambda x: gen_base(TEN * math.sin(math.radians(x))), math.asin)
    CoSin = ScaleFN(lambda x: gen_base(TEN * math.cos(math.radians(x))), math.acos, is_increasing=False)
    Tan = ScaleFN(lambda x: gen_base(TEN * math.tan(math.radians(x))), lambda p: math.atan(pos_base(p)))
    SinTan = ScaleFN(lambda x: scale_sin_tan_radians(math.radians(x)), lambda p: math.atan(pos_base(p)))
    SinTanRadians = ScaleFN(scale_sin_tan_radians, lambda p: math.atan(pos_base(math.degrees(p))), min_x=1e-5)
    CoTan = ScaleFN(lambda x: gen_base(TEN * math.tan(math.radians(angle_opp(x)))),
                    lambda p: math.atan(pos_base(angle_opp(p))), is_increasing=False)
    SinH = ScaleFN(lambda x: gen_base(math.sinh(x)), lambda p: math.asinh(pos_base(p)), min_x=ε)
    CosH = ScaleFN(lambda x: gen_base(math.cosh(x)), lambda p: math.acosh(pos_base(p)), min_x=ε)
    TanH = ScaleFN(lambda x: gen_base(math.tanh(x)), lambda p: math.atanh(pos_base(p)), min_x=ε)
    Pythagorean = ScaleFN(lambda x: gen_base(math.sqrt(1 - (x ** 2))) + 1,
                          lambda p: math.sqrt(1 - (pos_base(p) / 10) ** 2),
                          is_increasing=False, min_x=-1 + 1e-16, max_x=1 - 1e-16)
    Chi = ScaleFN(lambda x: x / PI_HALF, lambda p: p * PI_HALF)
    Theta = ScaleFN(lambda x: x / DEG_RT, lambda p: p * DEG_RT)
    LogLog = ScaleFN(lambda x: gen_base(math.log(x)), lambda p: math.exp(pos_base(p)), min_x=1 + 1e-15)
    LogLogNeg = ScaleFN(lambda x: gen_base(-math.log(x)), lambda p: math.exp(pos_base(-p)),
                        is_increasing=False, min_x=ε, max_x=1 - 1e-16)
    Hyperbolic = ScaleFN(lambda x: gen_base(math.sqrt((x ** 2) - 1)), lambda p: math.hypot(1, pos_base(p)),
                         min_x=1 + 1e-15)


@dataclass
class Scale:
    """Labeling and basic layout for a given invertible Scaler function."""
    left_sym: str
    """left scale symbol"""
    right_sym: str
    """right scale symbol"""
    scaler: ScaleFN
    gen_fn: callable = None
    """generating function (producing a fraction of output width)"""
    pos_fn: callable = None
    """positioning function (takes a proportion of output width, returning what value is there)"""
    shift: float = 0
    """scale shift from left index (as a fraction of output width)"""
    is_increasing: bool = None
    """whether the scale values increase as inputs increase (from left to right)"""
    key: str = None
    """non-unicode name for keying/lookup"""  # TODO extend for all alternate namings?
    on_slide: bool = False
    """whether the scale is meant to be on the slide; implying slide vs stator"""
    opp_key: str = None
    """which scale, if on an edge, it's aligned with"""
    mirror_key: str = None
    """which scale, mathematically, can be assigned numbers going the opposite direction on the ticks"""
    ex_start_value: float = None
    """which value, if the scale is displayed extended at start, to show first"""
    ex_end_value: float = None
    """which value, if the scale is displayed extended at end, to show last"""
    dividers: list = None
    """which values should the natural scale divide its graduated patterns at"""
    marks: list = None
    """which GaugeMarks deserve ticks and labels"""
    numerals: list = None
    """which numerals to label which otherwise wouldn't be"""

    min_overhang_frac = 0.02

    def __post_init__(self):
        scaler = self.scaler
        self.gen_fn = scaler.fn
        self.pos_fn = scaler.inverse
        if self.is_increasing is None:
            self.is_increasing = scaler.is_increasing
        if self.key is None:
            self.key = self.left_sym

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        return self.key == other.key

    def displays_cyclic(self):
        return self.scaler in {ScaleFNs.Base, ScaleFNs.Inverse, ScaleFNs.Square, ScaleFNs.Cube}

    def can_spiral(self):
        return self.scaler in {ScaleFNs.LogLog, ScaleFNs.LogLogNeg}

    def can_overhang(self):
        return ((self.ex_end_value and self.frac_pos_of(self.ex_end_value) > 1 + self.min_overhang_frac)
                or (self.ex_start_value and self.frac_pos_of(self.ex_start_value) < -self.min_overhang_frac))

    def frac_pos_of(self, x, shift_adj=0) -> float:
        """
        Generating Function for the Scales, scaled so 0..1 is the left to right of the scale
        :param float x: the dependent variable
        :param float shift_adj: how much the scale is shifted, as a fraction of the scale
        """
        return self.shift + shift_adj + self.gen_fn(x)

    def value_at_frac_pos(self, frac_pos: float, shift_adj=0) -> float:
        return self.pos_fn(frac_pos - self.shift - shift_adj)

    def value_at_start(self):
        return self.value_at_frac_pos(0)

    def value_at_end(self):
        return self.value_at_frac_pos(1)

    def value_range(self):
        return self.value_at_start(), self.value_at_end()

    def powers_of_ten_in_range(self):
        start_value, end_value = self.value_range()
        start_log = math.log10(start_value) if start_value > 0 else LOG_ZERO
        end_log = math.log10(end_value) if end_value > 0 else LOG_ZERO
        low_log = min(start_log, end_log)
        high_log = max(start_log, end_log)
        if high_log - low_log == math.inf:
            return None
        return range(math.ceil(low_log), math.ceil(high_log))

    def pos_of(self, x, geom) -> int:
        return round(geom.SL * self.frac_pos_of(x))

    def offset_between(self, x_start, x_end, scale_width):
        return abs(self.frac_pos_of(self.scaler.clamp_input(x_end))
                   - self.frac_pos_of(self.scaler.clamp_input(x_start))) * scale_width

    def min_offset_for_delta(self, x_start, x_end, x_delta, scale_width=1):
        return min(
            self.offset_between(x_start, x_start + x_delta, scale_width=scale_width),
            self.offset_between(x_end - x_delta, x_end, scale_width=scale_width)
        )

    def scale_to(self, x, scale_w, shift_adj=0) -> int:
        """
        Generating Function for the Scales
        :param float x: the dependent variable
        :param float shift_adj: how much the scale is shifted, as a fraction of its width
        :param int scale_w: scale width in pixels
        :returns: The number of pixels across to the result position
        """
        return round(scale_w * self.frac_pos_of(x, shift_adj=shift_adj))

    def grad_pat_default(self, r, y_off, al, extended=True):
        """graduated pattern, with as many defaults as can be inferred from the scale itself"""
        start_value = self.ex_start_value or self.value_at_start() if extended else None
        end_value = self.ex_end_value or self.value_at_end() if extended else None
        dividers = self.dividers
        if not dividers:
            powers = self.powers_of_ten_in_range()
            if powers:
                dividers = [10 ** n for n in powers]
        if dividers:
            r.pat_auto(y_off, self, al, x_start=start_value, x_end=dividers[0])
            last_i = len(dividers) - 1
            for i, di in enumerate(dividers):
                is_last = i >= last_i
                dj = end_value if is_last else dividers[i + 1]
                r.pat_auto(y_off, self, al, x_start=di, x_end=dj, include_last=is_last)
        else:
            r.pat_auto(y_off, self, al, x_start=start_value, x_end=end_value, include_last=True)

    def band_bg(self, r, y_off, color, start_value=None, end_value=None):
        geom = r.geometry
        li = geom.li
        if start_value is None:
            start_value = self.value_at_start()
        if end_value is None:
            end_value = self.value_at_end()
        start_pos = self.pos_of(start_value, geom)
        r.fill_rect(li + start_pos, y_off, self.pos_of(end_value, geom) - start_pos, geom.scale_h(self), color)


pi_fold_shift = ScaleFNs.Inverse(PI)


class Scales:
    A = Scale('A', 'x²', ScaleFNs.Square, opp_key='B', marks=[Marks.pi])
    B = Scale('B', 'x²_y', ScaleFNs.Square, on_slide=True, opp_key='A', marks=A.marks)
    BI = Scale('BI', '1/x²_y', ScaleFNs.InverseSquare, on_slide=True)
    C = Scale('C', 'x_y', ScaleFNs.Base, on_slide=True, opp_key='D', marks=[Marks.pi, Marks.deg_per_rad, Marks.tau])
    CF = Scale('CF', 'πx_y', ScaleFNs.Base, shift=pi_fold_shift, on_slide=True, opp_key='DF',
               marks=[Marks.pi, replace(Marks.pi, value=Marks.pi.value/TEN)])
    DF = Scale('DF', 'πx', ScaleFNs.Base, shift=pi_fold_shift, opp_key='CF', marks=CF.marks)
    CI = Scale('CI', '1/x_y', ScaleFNs.Inverse, on_slide=True, opp_key='DI', marks=CF.marks)
    CIF = Scale('CIF', '1/πx_y', ScaleFNs.Inverse, shift=pi_fold_shift - 1, on_slide=True, marks=C.marks)
    D = Scale('D', 'x', ScaleFNs.Base, opp_key='C', marks=C.marks)
    DI = Scale('DI', '1/x', ScaleFNs.Inverse, opp_key='CI', marks=C.marks)
    K = Scale('K', 'x³', ScaleFNs.Cube)
    L = Scale('L', 'log x', ScaleFNs.Log10)
    Ln = Scale('Ln', 'ln x', ScaleFNs.Ln)
    LL0 = Scale('LL₀', 'e^0.001x', ScaleFNs.LogLog, shift=3, key='LL0',
                dividers=[1.002, 1.004, 1.010], ex_start_value=1.00095, ex_end_value=1.0105)
    LL1 = Scale('LL₁', 'e^0.01x', ScaleFNs.LogLog, shift=2, key='LL1',
                dividers=[1.02, 1.05, 1.10], ex_start_value=1.0095, ex_end_value=1.11)
    LL2 = Scale('LL₂', 'e^0.1x', ScaleFNs.LogLog, shift=1, key='LL2',
                dividers=[1.2, 2], ex_start_value=1.1, ex_end_value=3, marks=[Marks.e])
    LL3 = Scale('LL₃', 'e^x', ScaleFNs.LogLog, key='LL3',
                dividers=[3, 6, 10, 50, 100, 1000, 10000], ex_start_value=2.5, ex_end_value=1e5, marks=[Marks.e])
    LL00 = Scale('LL₀₀', 'e^-0.001x', ScaleFNs.LogLogNeg, shift=3, key='LL00',
                 dividers=[0.998], ex_start_value=0.989, ex_end_value=0.9991)
    LL01 = Scale('LL₀₁', 'e^-0.01x', ScaleFNs.LogLogNeg, shift=2, key='LL01',
                 dividers=[0.95, 0.98], ex_start_value=0.9, ex_end_value=0.9906)
    LL02 = Scale('LL₀₂', 'e^-0.1x', ScaleFNs.LogLogNeg, shift=1, key='LL02',
                 dividers=[0.8, 0.9], ex_start_value=0.35, ex_end_value=0.91, marks=[Marks.inv_e])
    LL03 = Scale('LL₀₃', 'e^-x', ScaleFNs.LogLogNeg, key='LL03',
                 dividers=[5e-4, 1e-3, 1e-2, 0.1], ex_start_value=1e-4, ex_end_value=0.39, marks=[Marks.inv_e])
    P = Scale('P', '√1-(0.1x)²', ScaleFNs.Pythagorean, key='P',
              dividers=[0.3, 0.6, 0.8, 0.9, 0.98, 0.99], ex_start_value=0.1, ex_end_value=.995)
    R1 = Scale('R₁', '√x', ScaleFNs.SquareRoot, key='R1', marks=[Marks.sqrt_ten])
    R2 = Scale('R₂', '√10x', ScaleFNs.SquareRoot, key='R2', shift=-1, marks=R1.marks)
    S = Scale('S', '∡sin x°', ScaleFNs.Sin, mirror_key='CoS')
    CoS = Scale('C', '∡cos x°', ScaleFNs.CoSin, key='CoS', mirror_key='S')
    # SRT = Scale('SRT', '∡tan 0.01x', ScaleFNs.SinTanRadians)
    ST = Scale('ST', '∡tan 0.01x°', ScaleFNs.SinTan)
    T = Scale('T', '∡tan x°', ScaleFNs.Tan, mirror_key='CoT')
    CoT = Scale('CoT', '∡cot x°', ScaleFNs.CoTan, key='CoT', is_increasing=True, mirror_key='T', shift=-1)
    T1 = replace(T, left_sym='T₁', key='T1')
    T2 = replace(T, left_sym='T₂', right_sym='∡tan 0.1x°', key='T2', shift=-1, mirror_key='CoT2')
    W1 = Scale('W₁', '√x', ScaleFNs.SquareRoot, key='W1', opp_key='W1Prime', dividers=[1, 2],
               ex_start_value=0.95, ex_end_value=3.38, marks=[Marks.sqrt_ten])
    W1Prime = replace(W1, left_sym="W'₁", key='W1Prime', opp_key='W1')
    W2 = Scale('W₂', '√10x', ScaleFNs.SquareRoot, key='W2', shift=-1, opp_key='W2Prime', dividers=[5],
               ex_start_value=3, ex_end_value=10.66, marks=W1.marks)
    W2Prime = replace(W2, left_sym="W'₂", key='W2Prime', opp_key='W2')

    H1 = Scale('H₁', '√1+0.1x²', ScaleFNs.Hyperbolic, key='H1', shift=1, dividers=[1.03, 1.1], numerals=[1.005])
    H2 = Scale('H₂', '√1+x²', ScaleFNs.Hyperbolic, key='H2', dividers=[4])
    Sh1 = Scale('Sh₁', 'sinh x', ScaleFNs.SinH, key='Sh1', shift=1, dividers=[0.2, 0.4])
    Sh2 = Scale('Sh₂', 'sinh x', ScaleFNs.SinH, key='Sh2')
    Ch1 = Scale('Ch', 'cosh x', ScaleFNs.CosH, dividers=[1, 2], ex_start_value=0.01)
    Th = Scale('Th', 'tanh x', ScaleFNs.TanH, shift=1, dividers=[0.2, 0.4, 1, 2], ex_end_value=3)

    # EE-specific
    # Hemmi 153:
    Chi = Scale('χ', '', ScaleFNs.Chi, marks=[Marks.pi_half])
    Theta = Scale('θ', '°', ScaleFNs.Theta, key='Theta')
    # Pickett N-515-T:
    f_x = Scale('f_x', 'x/2π', ScaleFNs.Base, shift=gen_base(TAU), dividers=[0.2, 0.5, 1])
    L_r = Scale('L_r', '1/(2πx)²', ScaleFNs.InverseSquare, shift=gen_base(1 / TAU),
                dividers=[0.05, 0.1, 0.2, 0.5, 1, 2], ex_start_value=0.025, ex_end_value=2.55)


shift_360 = ScaleFNs.Inverse(3.6)


class AristoCommerzScales:
    """scales from Aristo 965 Commerz II: KZ, %, Z/ZZ1/ZZ2/ZZ3 compound interest"""
    Z = replace(Scales.D, left_sym='Z', right_sym='', opp_key='T1', dividers=[2, 4])
    T1 = replace(Z, left_sym='T₁', key='T1', opp_key='Z', on_slide=True)
    P1 = replace(Scales.CI, left_sym='P₁', right_sym='', key='P1', on_slide=True, dividers=[2, 4])
    KZ = replace(Scales.CF, left_sym='KZ', right_sym='', key='KZ', shift=shift_360,
                 ex_start_value=0.3, ex_end_value=4, dividers=[0.4, 1, 2])
    T2 = replace(KZ, left_sym='T₂', key='T2', on_slide=True)
    P2 = replace(Scales.CIF, left_sym='P₂', right_sym='', key='P2', shift=shift_360 - 1, on_slide=True,
                 ex_start_value=0.25, ex_end_value=3.3, dividers=[0.4, 1, 2])
    Pct = Scale(left_sym='p%', right_sym='', on_slide=True, shift=shift_360,
                scaler=ScaleFN(lambda x: gen_base((x + HUNDRED) / HUNDRED),
                               lambda p: pos_base(p) * HUNDRED - HUNDRED),
                dividers=[0], ex_start_value=-50, ex_end_value=100)
    # meta-scale showing % with 100% over 1/unity
    # special marks being 0,5,10,15,20,25,30,33⅓,40,50,75,100 in both directions
    Libra = replace(Scales.L, left_sym='£', right_sym='', key='Libra')


SCALE_NAMES = set(keys_of(Scales) + keys_of(AristoCommerzScales))


class Layout:
    def __init__(self, front_str: str, rear_str: str = None, scale_ns: object = Scales, align_overrides=None):
        if align_overrides is None:
            align_overrides = {}
        if not rear_str and '\n' in front_str:
            (front_str, rear_str) = front_str.splitlines()
        self.sc_keys: dict[Side, dict[RulePart, list[str]]] = {
            Side.FRONT: self.parse_side_layout(front_str),
            Side.REAR: self.parse_side_layout(rear_str)
        }
        self.scale_ns: object = scale_ns
        self.check_scales()
        self.scale_aligns: dict[Side, dict[str, Align]] = {
            Side.FRONT: align_overrides.get(Side.FRONT, {}), Side.REAR: align_overrides.get(Side.REAR, {})}
        self.infer_aligns()

    def __repr__(self):
        return f'Layout({self.sc_keys})'

    @classmethod
    def parse_segment_layout(cls, segment_layout: str) -> [str]:
        if segment_layout:
            return re.split(r'[, ]+', segment_layout.strip(' '))
        return None

    @classmethod
    def parts_of_side_layout(cls, side_layout: str) -> [str]:
        side_layout = side_layout.strip(' |')
        parts = None
        if '/' in side_layout:
            parts = side_layout.split('/', 2)
        elif '[' in side_layout and ']' in side_layout:
            parts = re.split(r'[\[\]]', side_layout, 2)
        if parts:
            return [x.strip() for x in parts]
        return [side_layout, '', '']

    @classmethod
    def parse_side_layout(cls, layout: str) -> dict[RulePart, [str]]:
        top_scales = None
        bottom_scales = None
        slide_scales = None
        if layout:
            major_parts = [cls.parse_segment_layout(x) for x in cls.parts_of_side_layout(layout.strip(' |'))]
            num_parts = len(major_parts)
            if num_parts == 1:
                (slide_scales) = major_parts
            elif num_parts == 3:
                (top_scales, slide_scales, bottom_scales) = major_parts
        return {RulePart.STATOR_TOP: top_scales, RulePart.SLIDE: slide_scales, RulePart.STATOR_BOTTOM: bottom_scales}

    def sc_keys_at(self, side: Side, part: RulePart):
        return self.sc_keys[side][part]

    def sc_keys_in_order(self):
        for side in Side:
            for part in RulePart:
                for sc_key in self.sc_keys_at(side, part) or ():
                    yield sc_key

    def check_scales(self):
        for scale_name in self.sc_keys_in_order():
            if not (hasattr(self.scale_ns, scale_name) or hasattr(Rulers, scale_name)):
                raise ValueError(f'Unrecognized front scale name: {scale_name}')

    def scales_at(self, side: Side, part: RulePart) -> list[Scale]:
        return [getattr(self.scale_ns, sc_name, None) or getattr(Rulers, sc_name, None)
                for sc_name in self.sc_keys[side][part] or []]

    def infer_aligns(self):
        """Fill scale alignments per the layout into the overrides."""
        for side in Side:
            side_overrides = self.scale_aligns[side]
            side_seen = set()
            for part in RulePart:
                part_scales = self.scales_at(side, part)
                last_i = len(part_scales) - 1
                for i, sc in enumerate(part_scales):
                    if sc.key not in side_overrides:
                        if isinstance(sc, Ruler):  # rulers are always edge-aligned
                            side_overrides[sc.key] = Align.UPPER if part == RulePart.STATOR_TOP else Align.LOWER
                        elif i == 0 and part == RulePart.SLIDE:
                            side_overrides[sc.key] = Align.UPPER
                        elif i == last_i and part != RulePart.STATOR_BOTTOM:
                            side_overrides[sc.key] = Align.LOWER
                        elif sc.opp_key:
                            side_overrides[sc.key] = Align.UPPER if sc.opp_key in side_seen else Align.LOWER
                    side_seen.add(sc.key)

    def scale_al(self, sc: Scale, side: Side, part: RulePart):
        default_al = Align.UPPER if part == RulePart.STATOR_BOTTOM else Align.LOWER
        return self.scale_aligns[side].get(sc.key, default_al)


@dataclass(frozen=True)
class Ruler:
    """
    Rulers are geometry-dependent scales that appear only on the edges of a model per side.
    Like a scale, it has a tick pattern. Unlike a scale, it only aligns with the geometry itself.
    Also, tick placement is physically-oriented, so we need to avoid numeric error.
    """
    key: str = 'px'
    tick_pattern: TickFactors = TF_BY_MIN[1]
    left_offset: float = 0.0
    """margin from left side of Geometry in units"""
    num_units: int = 1000
    """number of units to show; should be generated or at least limited from geometry"""
    pixels_per_unit: float = 1

    def pos_of(self, x_cm):
        return (self.left_offset + x_cm) * self.pixels_per_unit

    def value_at(self, x):
        return (x / self.pixels_per_unit) - self.left_offset

    @property
    def is_increasing(self):
        return True

    def pat(self, r: Renderer, y_off: int, al: Align):
        g = r.geometry
        li = g.li
        th1, th2, th3, th4 = (g.tick_h(HMod.LG), g.tick_h(HMod.MED), g.tick_h(HMod.XS), g.tick_h(HMod.DOT))
        font1, font2 = (r.style.font_for(FontSize.N_LG), None)
        scale_h = g.scale_h(self)
        sym_col = r.style.fg_col(self.key, is_increasing=self.is_increasing)
        tenth_col = r.style.decimal_color
        i_sf = self.tick_pattern[0] * self.tick_pattern[1] * self.tick_pattern[2]
        step1, step2, step3, _ = t_s(i_sf, self.tick_pattern)
        num_units = min(self.num_units, int(g.side_w / self.pixels_per_unit - self.left_offset))
        for i in range(0, num_units * i_sf + 1):
            num = i / i_sf
            x = self.pos_of(num) - li
            tick_h = th4
            if i % step1 == 0:
                tick_h = th1
                if font1:
                    r.draw_numeral(num, y_off, sym_col, scale_h, x, th1, font1, al)
            elif i % step2 == 0:
                tick_h = th2
                if font2:
                    r.draw_numeral(last_digit_of(num), y_off, tenth_col, scale_h, x, th2, font2, al)
            elif i % step3 == 0:
                tick_h = th3
            r.draw_tick(y_off, x, tick_h, sym_col, scale_h, al)


class Rulers:
    PT = Ruler('pt', TF_BY_MIN[10], num_units=25 * 72, pixels_per_unit=Geometry.PixelsPerIN // 72)
    CM = Ruler('cm', TF_BY_MIN[20], 1.5, 30, Geometry.PixelsPerCM)
    IN_DEC = Ruler('in', TF_BY_MIN[50], 0.5, 12, Geometry.PixelsPerIN)
    IN_BIN = Ruler('in', TF_BIN, 0.5, 12, Geometry.PixelsPerIN)
    IN = IN_DEC


# --------------------------6. Models----------------------------


class Layouts:
    MannheimOriginal = Layout('A/B C/D', '')
    RegleDesEcoles = Layout('DF/CF C/D', '')
    Mannheim = Layout('A/B CI C/D K', '[S L T]')
    Rietz = Layout('K A/B CI C/D L', '[S ST T]')
    Darmstadt = Layout('K A/B K CI C/D P', '[LL1 LL2 LL3]')
    DarmstadtAdvanced = Layout('T K A/B BI CI C/D P S', '[ L LL0 LL1 LL2 LL3 ]')


@dataclass(frozen=True)
class Model:
    brand: str
    subtitle: str
    name: str
    geometry: Geometry
    layout: Layout
    style: Style = Styles.Default

    def scale_h_per(self, side: Side, part: RulePart):
        result = 0
        for sc in self.layout.scales_at(side, part):
            result += self.geometry.scale_margin(sc, side)
            result += self.geometry.scale_h(sc, side)
        return result

    def auto_stock_h(self):
        result = 0
        for side in Side:
            for part in RulePart.STATOR_TOP, RulePart.STATOR_BOTTOM:
                result = max(result, self.scale_h_per(side, part))
        return result

    def auto_slide_h(self):
        result = 0
        for side in Side:
            result = max(result, self.scale_h_per(side, RulePart.SLIDE))
        return result


class Models:
    Demo = Model('KWENA & TOOR CO.', 'LEFT HANDED LIMAÇON 2020', 'BOGELEX 1000',
                 Geometry((8000, 1600),
                          (100, 100),
                          Geometry.DEFAULT_SCALE_WH,
                          Geometry.DEFAULT_TICK_WH,
                          640,
                          top_margin=109,
                          margin_overrides={Side.REAR: {80: ['DI']}}),
                 Layout('|  L,  DF [ CF,CIF,CI,C ] D, R1, R2 |',
                        '|  K,  A  [ B, T, ST, S ] D,  DI    |',
                        align_overrides={Side.FRONT: {'CIF': Align.UPPER},
                                         Side.REAR: {'D': Align.UPPER, 'DI': Align.UPPER}}))

    MannheimOriginal = Model('Mannheim', 'Demo', 'Original',
                             Geometry((8000, 1000),
                                      (100, 100),
                                      Geometry.DEFAULT_SCALE_WH,
                                      Geometry.DEFAULT_TICK_WH,
                                      round(Geometry.SH * 2.5),
                                      top_margin=109),
                             Layouts.MannheimOriginal)

    Ruler = replace(MannheimOriginal,
                    layout=Layout('IN [] CM'))
    MannheimWithRuler = replace(MannheimOriginal,
                                layout=Layout('A/B C/D', 'IN [] CM'))

    Aristo868 = Model('Aristo', '', '868',
                      Geometry((8000, 1860),
                               (100, 100),
                               (Geometry.SL, 120),
                               Geometry.DEFAULT_TICK_WH,
                               590,
                               top_margin=0),
                      Layout(
                          'ST T1 T2 DF/CF CIF CI C/D P S',
                          'LL01 LL02 LL03 A/B L K C/D LL3 LL2 LL1'
                      ),
                      Style(font_family=Font.CMUBright))

    Aristo965 = Model('Aristo', 'Commerz II', '965',
                      Geometry((8000, 1200),  # 30cm (8000px) x 5cm (1333px)
                               (100, 100),
                               (6666, 80),  # 25cm (6666.7px) x 3.5mm (93px)
                               Geometry.DEFAULT_TICK_WH,
                               480  # 1.7cm (450px)
                               ),
                      Layout('Pct KZ [T2 P2 P1 T1] Z', '', scale_ns=AristoCommerzScales,
                             align_overrides={Side.FRONT: {'P2': Align.UPPER}}),
                      Style(decreasing_color=Colors.SYM_GREEN, font_family=Font.CMUBright,
                            overrides={
                                'T1': {'color': Colors.RED},
                                'T2': {'color': Colors.RED}
                            }))

    PickettN515T = Model('Pickett', '', 'N-515-T',
                         Geometry((8000, 2000),
                                  (100, 100),
                                  Geometry.DEFAULT_SCALE_WH,
                                  Geometry.DEFAULT_TICK_WH,
                                  Geometry.SH * 5),
                         Layout(
                             'L_r f_x A/B S T CI C/D L Ln', ''
                         ),
                         Styles.PickettEyeSaver)
    FaberCastell283 = Model('Faber-Castell', '', '2/83',
                            Geometry((8800, 1280),  # 33cm (px) x 4.8cm (1280px)
                                     (100, 100),
                                     (6666, 101),  # 25cm (6666.7px) x 3.5mm (93px)
                                     Geometry.DEFAULT_TICK_WH,
                                     400,  # 1.5cm (400px)
                                     top_margin=0,
                                     scale_h_overrides={
                                         Side.FRONT: {72: ['K', 'T1', 'T2', 'P']},
                                         Side.REAR: {90: ['LL03', 'LL02', 'LL01', 'LL1', 'LL2', 'LL3']}
                                     }),
                            Layout(
                                'K T1 T2 DF/CF CIF CI C/D S ST P',
                                'LL03 LL02 LL01 W2/W2Prime L C W1Prime/W1 LL1 LL2 LL3',
                                align_overrides={
                                    Side.FRONT: {
                                        'T2': Align.UPPER,
                                        'CI': Align.UPPER,
                                        'DF': Align.LOWER,
                                        'S': Align.LOWER,
                                    },
                                    Side.REAR: {'C': Align.UPPER}
                                }
                            ),
                            Style(font_family=Font.CMUBright,
                                  bg_colors={
                                      'C': Colors.FC_LIGHT_GREEN_BG,
                                      'CF': Colors.FC_LIGHT_GREEN_BG
                                  }
                                  ))
    FaberCastell283N = Model('Faber-Castell', '', '2/83N',
                             Geometry((9866, 1520),  # 37cm (9866px) x 5.7cm (1520px)
                                      (0, 0),
                                      (6666, 101),  # 25cm (6666.7px) x 3.5mm (93px)
                                      (Geometry.STT, 50),
                                      510,  # 1.9cm (506.6px)
                                      top_margin=0,
                                      scale_h_overrides={
                                          Side.REAR: {
                                              74: ['LL0', 'LL1', 'LL2', 'LL3',
                                                   'LL00', 'LL01', 'LL02', 'LL03']
                                          }
                                      }),
                             Layout(
                                 'T1 T2 K A DF [CF B CIF CI C] D DI S ST P',
                                 'LL03 LL02 LL01 LL00 W2 [W2Prime CI L C W1Prime] W1 D LL0 LL1 LL2 LL3',
                                 align_overrides={
                                     Side.FRONT: {
                                         'T2': Align.UPPER,
                                         'CI': Align.UPPER,
                                         'S': Align.LOWER,
                                     },
                                     Side.REAR: {
                                         'LL03': Align.LOWER,
                                         'LL02': Align.UPPER,
                                         'LL01': Align.LOWER,
                                         'LL00': Align.UPPER,
                                         'C': Align.UPPER,
                                         'LL0': Align.LOWER,
                                         'LL1': Align.UPPER,
                                         'LL2': Align.LOWER,
                                         'LL3': Align.UPPER,
                                     }
                                 }
                             ),
                             Style(bg_colors={
                                 'C': Colors.FC_LIGHT_GREEN_BG,
                                 'CF': Colors.FC_LIGHT_GREEN_BG,
                                 'A': Colors.FC_LIGHT_BLUE_BG,
                                 'B': Colors.FC_LIGHT_BLUE_BG,
                                 'LL0': Colors.FC_LIGHT_GREEN_BG
                             }, font_family=Font.CMUBright))

    Graphoplex621 = Model('Graphoplex', '', '621',
                          Geometry((7740, 1070),  # 29cm (7733px) x 40cm (1066px)
                                   (100, 100),
                                   (6666, 80),  # 25cm (6666.7px) x 3.5mm (93px)
                                   Geometry.DEFAULT_TICK_WH,
                                   480,  # 1.8cm
                                   scale_h_overrides={
                                       Side.FRONT: {
                                           70: ['P', 'ST', 'K', 'L']
                                       }
                                   }),
                          Layout(
                              'P ST A [ B T1 S CI C ] D K L',  # 'P SRT A [ B T1 S CI C ] D K L'
                              ''
                          ), Styles.Graphoplex)


def gen_scale(r: Renderer, y_off: int, sc: Scale, al=None, overhang=None, side: Side = None):
    geom = r.geometry
    style = r.style
    if style.override_for(sc.key, 'hide', False):
        return

    if not overhang:  # fraction of total width to overhang each side to label
        overhang = 0.07 if sc.can_spiral() or sc.can_overhang() else 0.02

    scale_h = geom.scale_h(sc, side=side)
    scale_h_ratio = geom.scale_h_ratio(sc, side=side)

    # Place Index Symbols (Left and Right)
    italic = FontStyle.ITALIC
    f_lbl = style.font_for(FontSize.SC_LBL if scale_h > FontSize.SC_LBL.value * 1.5 else scale_h // 2)
    f_lbl_s = style.font_for(FontSize.N_XL if scale_h > FontSize.N_XL.value * 2 else scale_h // 2)
    f_xln = style.font_for(FontSize.N_XL, h_ratio=scale_h_ratio)
    f_lgn = style.font_for(FontSize.N_LG, h_ratio=scale_h_ratio)
    f_mdn = style.font_for(FontSize.N_MD, h_ratio=scale_h_ratio)
    f_smn = style.font_for(FontSize.N_SM, h_ratio=scale_h_ratio)
    f_mdn_i = style.font_for(FontSize.N_MD, font_style=italic, h_ratio=scale_h_ratio)
    f_md2 = style.font_for(50, h_ratio=scale_h_ratio)
    f_md2_i = style.font_for(50, font_style=italic, h_ratio=scale_h_ratio)

    li = geom.li
    scale_w = geom.SL
    if DEBUG:
        r.draw_box(li, y_off, scale_w, scale_h, 'grey')

    sym_col = style.fg_col(sc.key, is_increasing=sc.is_increasing)
    bg_col = style.bg_col(sc.key)
    if bg_col:
        sc.band_bg(r, y_off, bg_col)

    # Right
    f_lbl_r = f_lbl_s if len(sc.right_sym) > 6 or '^' in sc.right_sym else f_lbl
    (right_sym, _, _) = symbol_parts(sc.right_sym)
    w2, h2 = style.sym_dims(right_sym, f_lbl_r)
    y2 = (geom.SH - h2) / 2  # Ignore custom height/spacing for legend symbols
    x_right = (1 + overhang) * scale_w + w2 / 2
    r.draw_sym_al(sc.right_sym, y_off, sym_col, scale_h, x_right, y2, f_lbl_r, al)

    # Left
    (left_sym, _, _) = symbol_parts(sc.left_sym)
    w1, h1 = style.sym_dims(left_sym, f_lbl)
    y1 = (geom.SH - h1) / 2  # Ignore custom height/spacing for legend symbols
    x_left = (0 - overhang) * scale_w - w1 / 2
    r.draw_sym_al(sc.left_sym, y_off, sym_col, scale_h, x_left, y1, f_lbl, al)

    # Special Symbols for S, and T
    sc_alt: Scale = getattr(Scales, sc.mirror_key, None) if sc.mirror_key else None
    if sc_alt:
        alt_col = style.fg_col(sc_alt.key, is_increasing=not sc_alt.is_increasing)
        r.draw_sym_al(sc_alt.left_sym, y_off, alt_col, scale_h, x_left - style.sym_width('__', f_lbl), y2, f_lbl, al)
        r.draw_sym_al(sc_alt.right_sym, y_off, alt_col, scale_h, x_right, y2 - h2 * 0.8, f_lbl_r, al)
    elif sc == Scales.ST:
        r.draw_sym_al('∡sin 0.01x°', y_off, sym_col, scale_h, x_right, y2 - h2 * 0.8, f_lbl_r, al)

    th_med = geom.tick_h(HMod.MED)
    th_xl = geom.tick_h(HMod.XL)
    th_lg = geom.tick_h(HMod.LG)
    th_sm = geom.tick_h(HMod.SM)
    th_xs = geom.tick_h(HMod.XS)
    th_dot = geom.tick_h(HMod.DOT)

    # Tick Placement (the bulk!)
    fonts_lbl = (f_lbl, None, None)
    fonts2 = (f_lbl, f_mdn, None)
    fonts_xl = (f_xln, None, None)
    ths1 = (th_med, th_xl, th_sm, th_xs)
    ths2 = (th_med, th_xl, th_xs, th_xs)
    ths3 = (th_med, th_sm, th_sm, th_xs)
    ths4 = (th_med, th_xl, th_sm, th_dot)
    fonts_no = (None, None, None)
    sf = 1000  # Reflects the minimum significant figures needed for standard scales to avoid FP inaccuracy
    if (sc.scaler in {ScaleFNs.Base, ScaleFNs.Inverse}) and sc.shift == 0:  # C/D and CI/DI
        fp1, fp2, fp4, fpe = (fp * sf for fp in (1, 2, 4, 10))
        r.pat(y_off, sc, al, fp1, fp2, sf, t_s(sf, TF_BY_MIN[100]), ths3, fonts2, True)
        r.pat(y_off, sc, al, fp2, fp4, sf, t_s(sf, TF_BY_MIN[50]), ths1, fonts_lbl, False)
        r.pat(y_off, sc, al, fp4, fpe + 1, sf, t_s(sf, TF_BY_MIN[20]), ths1, fonts_lbl, True)
    elif sc.scaler == ScaleFNs.Square or sc == Scales.BI:
        for b in (sf * 10 ** n for n in range(0, 2)):
            fp1, fp2, fp3, fpe = (fp * b for fp in (1, 2, 5, 10))
            r.pat(y_off, sc, al, fp1, fp2, sf, t_s(b, TF_BY_MIN[50]), ths1, fonts_lbl, True)
            r.pat(y_off, sc, al, fp2, fp3, sf, t_s(b, TF_BY_MIN[20]), ths1, fonts_lbl, True)
            r.pat(y_off, sc, al, fp3, fpe + 1, sf, t_s(b, TF_BY_MIN[10]), ths2, fonts_lbl, True)

    elif sc == Scales.K:
        for b in (sf * (10 ** n) for n in range(0, 3)):
            fp1, fp2, fp3, fpe = (fp * b for fp in (1, 3, 6, 10))
            r.pat(y_off, sc, al, fp1, fp2, sf, t_s(b, TF_BY_MIN[20]), ths1, fonts_xl, True)
            r.pat(y_off, sc, al, fp2, fp3, sf, t_s(b, TF_BY_MIN[10]), ths2, fonts_xl, True)
            r.pat(y_off, sc, al, fp3, fpe + 1, sf, t_s(b, TF_BY_MIN[5]), ths2, fonts_xl, True)

    elif sc == Scales.R1:
        fp1, fp2, fpe = (int(fp * sf) for fp in (1, 2, 3.17))
        r.pat(y_off, sc, al, fp1, fp2, sf, t_s(sf // 10, TF_BY_MIN[20]), ths1, fonts_no, True)
        r.pat(y_off, sc, al, fp2, fpe + 1, sf, t_s(sf, TF_BY_MIN[100]), (th_med, th_med, th_sm, th_xs), fonts2, True)

        # 1-10 Labels
        for x in range(1, 2):
            r.draw_numeral(x, y_off, sym_col, scale_h, sc.pos_of(x, geom), th_med, f_lbl, al)
        # 1.1-1.9 Labels
        for x in (x / 10 for x in range(11, 20)):
            r.draw_numeral(last_digit_of(x), y_off, sym_col, scale_h, sc.pos_of(x, geom), th_med, f_lgn, al)

    elif sc == Scales.R2:
        fp1, fp2, fpe = (int(fp * sf) for fp in (3.16, 5, 10))
        r.pat(y_off, sc, al, fp1, fp2, sf, t_s(sf, TF_BY_MIN[100]), ths3, fonts2, True)
        r.pat(y_off, sc, al, fp2, fpe + 1, sf, t_s(sf, TF_BY_MIN[50]), ths1, fonts_lbl, True)

    elif (sc.scaler == ScaleFNs.Base and sc.shift == pi_fold_shift) or sc == Scales.CIF:  # CF/DF/CIF
        is_cif = sc == Scales.CIF
        fp1 = int((0.31 if is_cif else 0.314) * sf)
        i1 = sf // TEN
        fp2, fp3, fp4 = (fp * i1 for fp in (4, 10, 20))
        fpe = int(3.2 * sf) if is_cif else fp1 * TEN
        r.pat(y_off, sc, al, fp1, fp2, sf, t_s(i1, TF_BY_MIN[50]), ths1, fonts_lbl, True)
        r.pat(y_off, sc, al, fp2, fp3, sf, t_s(i1, TF_BY_MIN[20]), ths1, fonts_lbl, True)
        r.pat(y_off, sc, al, fp3, fp4, sf, t_s(sf, TF_BY_MIN[100]), ths3, fonts2, True)
        r.pat(y_off, sc, al, fp4, fpe + 1, sf, t_s(sf, TF_BY_MIN[50]), ths1, fonts_lbl, True)

    elif sc == Scales.L:
        r.pat(y_off, sc, al, 0, TEN * sf + 1, sf, t_s(sf, TF_BY_MIN[50]), (th_lg, th_xl, th_med, th_xs), fonts_no, True)
        for x in range(0, 11):
            r.draw_numeral(x / 10, y_off, sym_col, scale_h, sc.pos_of(x, geom), th_med, f_lbl, al)

    elif sc.scaler in {ScaleFNs.Sin, ScaleFNs.CoSin} or sc in {Scales.T, Scales.T1, Scales.CoT}:
        is_tan = sc.scaler in {ScaleFNs.Tan, ScaleFNs.CoTan}
        ths_z = (th_xl, th_sm, th_xs, th_xs)
        if is_tan:
            fp1, fp2, fp3, fpe = (int(fp * sf) for fp in (5.7, 10, 25, 45))
            fpe += 1
            r.pat(y_off, sc, al, fp1, fp2, sf, t_s(sf, TF_BY_MIN[20]), (th_xl, th_xl, th_sm, th_xs), fonts_no, True)
            r.pat(y_off, sc, al, fp2, fp3, sf, t_s(sf, TF_BY_MIN[10]), ths_z, fonts_no, True)
            r.pat(y_off, sc, al, fp3, fpe, sf, t_s(sf * 5, (5, 5, 1)), (th_xl, th_med, th_xs, th_xs), fonts_no, True)
        else:
            fp1, fp2, fp3, fp4, fp5, fpe = (int(fp * sf) for fp in (5.7, 20, 30, 60, 80, 90))
            fpe += 1
            r.pat(y_off, sc, al, fp1, fp2, sf, t_s(sf, TF_BY_MIN[10]), ths_z, fonts_no, True)
            r.pat(y_off, sc, al, fp2, fp3, sf, t_s(sf * 5, (5, 5, 1)), ths_z, fonts_no, True)
            r.pat(y_off, sc, al, fp3, fp4, sf, t_s(sf * 10, TF_BY_MIN[20]), (th_xl, th_xl, th_sm, th_xs), fonts_no, True)
            r.pat(y_off, sc, al, fp4, fp5, sf, t_s(sf * 10, TF_BY_MIN[10]), ths_z, fonts_no, True)
            r.pat(y_off, sc, al, fp5, fpe, sf, t_s(sf * 10, (2, 1, 1)), (th_med, th_sm, th_xs, th_xs), fonts_no, True)

        # Degree Labels
        f = geom.STH * 1.1 if is_tan else th_med
        range1 = range(6, 16)
        range2 = range(16, 21)
        alt_col = style.fg_col(sc_alt.key, is_increasing=not sc_alt.is_increasing)
        for x in chain(range1, range2, range(25, 41, 5), () if is_tan else range(50, 80, 10)):
            f_l = f_md2_i if x in range1 else f_mdn_i
            f_r = f_md2 if x in range1 else f_mdn
            x_coord = sc.pos_of(x, geom) + 1.2 / 2 * style.sym_width(str(x), f_l)
            r.draw_numeral(x, y_off, sym_col, scale_h, x_coord, f, f_r, al)
            if x not in range2:
                xi = angle_opp(x)
                x_coord_opp = sc.pos_of(x, geom) - 1.4 / 2 * style.sym_width(str(xi), f_l)
                r.draw_numeral(xi, y_off, alt_col, scale_h, x_coord_opp, f, f_l, al)

        r.draw_numeral(45 if is_tan else DEG_RT, y_off, sym_col, scale_h, scale_w, f, f_lgn, al)

    elif sc == Scales.T2:
        fp1, fp2, fpe = (int(fp * sf) for fp in (45, 75, angle_opp(5.7)))
        r.pat(y_off, sc, al, fp1, fp2, sf, t_s(sf * 5, (5, 2, 5)), ths4, fonts_xl, False)
        r.pat(y_off, sc, al, fp2, fpe, sf, t_s(sf * 5, (5, 2, 10)), ths4, fonts_xl, False)

    elif sc == Scales.ST:
        fp1, fp2, fp3, fp4, fpe = (int(fp * sf) for fp in (0.57, 1, 2, 4, 5.8))
        r.pat(y_off, sc, al, fp1, fp2, sf, t_s(sf, (20, 5, 2)), ths1, fonts_no, True)
        r.pat(y_off, sc, al, fp2, fp3, sf, t_s(sf // 10, (1, 2, 5)), ths1, fonts_no, True)
        r.pat(y_off, sc, al, fp3, fp4, sf, t_s(sf // 2, TF_BY_MIN[25]), ths1, fonts_no, True)
        r.pat(y_off, sc, al, fp4, fpe + 1, sf, t_s(sf, (1, 10, 2)), ths1, fonts_no, True)

        # Degree Labels
        r.draw_sym_al('1°', y_off, sym_col, scale_h, sc.pos_of(1, geom), th_med, f_lbl, al)
        for x in chain((x / 10 for x in range(6, 10)), (x + 0.5 for x in range(1, 4)), range(2, 6)):
            r.draw_numeral(x, y_off, sym_col, scale_h, sc.pos_of(x, geom), th_med, f_lbl, al)

    elif sc == AristoCommerzScales.Pct:
        if DEBUG:
            sc.grad_pat_default(r, y_off, al)
        for pct_value in (0, 5, 10, 15, 20, 35, 30, 40):
            r.draw_numeral(pct_value, y_off, sym_col, scale_h, sc.pos_of(pct_value, geom), 0, f_lgn, Align.LOWER)
            r.draw_numeral(pct_value, y_off, sym_col, scale_h, sc.pos_of(-pct_value, geom), 0, f_lgn, Align.LOWER)
        for sym, val in (('-50%', -50), ('50%', 50), ('-33⅓', -100/3), ('33⅓', 100/3), ('+100%', 100)):
            r.draw_sym_al(sym, y_off, sym_col, scale_h, sc.pos_of(val, geom), 0, f_lgn, Align.LOWER)

    else:  # Fallback to our generic algorithm, then fill in marks and numerals as helpful
        sc.grad_pat_default(r, y_off, al)

    if sc.marks:
        f_mark = f_lbl if sc.scaler in {ScaleFNs.Base, ScaleFNs.Inverse, ScaleFNs.Square} else f_lgn
        for mark in sc.marks:
            r.draw_mark(mark, y_off, sc, f_mark, al, sym_col, side=side)
    if sc.numerals:
        for x in sc.numerals:
            r.draw_numeral(x, y_off, sym_col, scale_h, sc.pos_of(x, geom), th_med, f_smn, al)


def first_digit_of(x) -> int:
    """First numeral in the digital representation of a number."""
    return int(str(x)[0])


def last_digit_of(x) -> int:
    """Last numeral in the digital representation of a number."""
    if int(x) == x:
        x = int(x)
    return int(str(x)[-1])


def sig_digit_of(num):
    """When only one digit will fit on a major scale's numerals, pick the most significant."""
    if not (num > 0 and math.log10(num).is_integer()):
        if num % 10 == 0:
            num = first_digit_of(num)
        elif num < 1:
            num = last_digit_of(num)
    else:
        num = first_digit_of(num)
    return num


class Mode(Enum):
    RENDER = 'render'
    DIAGNOSTIC = 'diagnostic'
    STICKERPRINT = 'stickerprint'


def transcribe(src_img: Image.Image, dst_img: Image.Image, src_x, src_y, size_x, size_y, target_x, target_y):
    """Transfer a pixel rectangle from a SOURCE (for rendering) to DESTINATION (for stickerprint)"""
    src_box = src_img.crop((src_x, src_y, src_x + size_x, src_y + size_y))
    dst_img.paste(src_box, (target_x, target_y))


def image_for_rendering(model: Model, w=None, h=None):
    geom = model.geometry
    return Image.new('RGB', (w or geom.total_w, h or geom.print_height), model.style.bg.value)


def save_png(img_to_save: Image, basename: str, output_suffix=None):
    output_filename = f"{basename}{'.' + output_suffix if output_suffix else ''}.png"
    from os.path import abspath
    output_full_path = abspath(output_filename)
    img_to_save.save(output_full_path, 'PNG')
    print(f'Result saved to: file://{output_full_path}')


# ----------------------7. Commands------------------------------------------


def main():
    """CLI processor for rendering the models in various modes."""
    import argparse
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('--mode',
                             choices=[m.value for m in Mode],
                             help='What to render')
    args_parser.add_argument('--model',
                             choices=keys_of(Models),
                             default='Demo',
                             help='Which sliderule model')
    args_parser.add_argument('--suffix',
                             help='Output filename suffix for variations')
    args_parser.add_argument('--test',
                             action='store_true',
                             help='Output filename for test comparisons')
    args_parser.add_argument('--cutoffs',
                             action='store_true',
                             help='Render the metal cutoffs')
    args_parser.add_argument('--debug',
                             action='store_true',
                             help='Render debug indications (corners and bounding boxes)')
    cli_args = args_parser.parse_args()
    render_mode: Mode = next(mode for mode in Mode if mode.value == cli_args.mode)
    model_name = cli_args.model
    model: Model = getattr(Models, model_name)
    output_suffix = cli_args.suffix or ('test' if cli_args.test else None)
    render_cutoffs = cli_args.cutoffs
    global DEBUG
    DEBUG = cli_args.debug

    start_time = time.time()

    sliderule_img = None
    if render_mode in {Mode.RENDER, Mode.STICKERPRINT}:
        sliderule_img = render_sliderule_mode(model, render_mode, sliderule_img, render_cutoffs=render_cutoffs)
        print(f'Slide Rule render finished at: {round(time.time() - start_time, 2)} seconds')
        if render_mode == Mode.RENDER:
            save_png(sliderule_img, f'{model_name}.SlideRuleScales', output_suffix)

    if render_mode == Mode.DIAGNOSTIC:
        diagnostic_img = render_diagnostic_mode(model, all_scales=model != Models.Demo)
        print(f'Diagnostic render finished at: {round(time.time() - start_time, 2)} seconds')
        save_png(diagnostic_img, f'{model_name}.Diagnostic', output_suffix)

    if render_mode == Mode.STICKERPRINT:
        stickerprint_img = render_stickerprint_mode(model, sliderule_img)
        print(f'Stickerprint render finished at: {round(time.time() - start_time, 2)} seconds')
        save_png(stickerprint_img, f'{model_name}.StickerCut', output_suffix)

    print(f'Program finished at: {round(time.time() - start_time, 2)} seconds')


def render_sliderule_mode(model: Model, render_mode: Mode, sliderule_img=None, render_cutoffs: bool = False):
    if not sliderule_img:
        sliderule_img = image_for_rendering(model)
    geom = model.geometry
    layout = model.layout
    y_front_start = geom.oY
    r = Renderer.make(sliderule_img, geom, model.style)
    y_rear_start = y_front_start + geom.side_h + geom.oY
    if render_mode == Mode.RENDER:
        for side in Side:
            y0 = y_front_start if side == Side.FRONT else y_rear_start
            r.draw_borders(y0, side)
            if render_cutoffs:
                r.draw_metal_cutoffs(y0, side)
    # Front Scale
    # Titling
    style = model.style
    f_lbl = style.font_for(FontSize.SC_LBL)
    side_w_q = geom.side_w // 4
    li = geom.li
    y_off = y_side_start = y_front_start
    if model == Models.Demo:
        upper = Align.UPPER
        y_off_titling = 25 + y_off
        title_col = Colors.RED
        r.draw_sym_al(model.name, y_off_titling, title_col, 0, side_w_q - li, 0, f_lbl, upper)
        r.draw_sym_al(model.subtitle, y_off_titling, title_col, 0, side_w_q * 2 - li + geom.oX, 0, f_lbl, upper)
        r.draw_sym_al(model.brand, y_off_titling, title_col, 0, side_w_q * 3 - li, 0, f_lbl, upper)
        y_off = y_off_titling + f_lbl.size
    # Scales
    for side in Side:
        for part in RulePart:
            part_scales = layout.scales_at(side, part)
            last_i = len(part_scales) - 1
            for i, sc in enumerate(part_scales):
                scale_h = geom.scale_h(sc, side)
                scale_al = layout.scale_al(sc, side, part)
                # Handle edge-aligned scales:
                if i == 0 and scale_al == Align.UPPER:
                    y_off = y_side_start + geom.edge_h(part, True)
                elif i == last_i and scale_al == Align.LOWER:
                    y_off = y_side_start + geom.edge_h(part, False) - scale_h
                else:  # Incremental displacement by default
                    y_off += geom.scale_margin(sc, side)
                if isinstance(sc, Scale):
                    gen_scale(r, y_off, sc, al=scale_al, side=side)
                elif isinstance(sc, Ruler):
                    sc.pat(r, y_off, scale_al)
                y_off += scale_h

        y_off = y_rear_start
        y_side_start = y_rear_start
        y_off += geom.top_margin
    return sliderule_img


def render_stickerprint_mode(model, sliderule_img):
    # Code Names
    # (fs) | UL,UM,UR [ ML,MM,MR ] LL,LM,LR |
    # (bs) | UL,UM,UR [ ML,MM,MR ] LL,LM,LR |
    # Front Scale, Back Scale
    # Upper Middle Lower, Left Middle Right
    # (18 total stickers)
    o_x2 = 50  # x dir margins
    o_y2 = 50  # y dir margins
    o_a = 50  # overhang amount
    ext = 20  # extension amount
    geom = model.geometry
    scale_w = 6500
    geom_s = Geometry(
        (scale_w, 1600),
        Geometry.NO_MARGINS,
        (scale_w, Geometry.SH),
        Geometry.DEFAULT_TICK_WH,
        640
    )
    style = model.style
    scale_h = geom_s.SH
    total_w = scale_w + 2 * o_x2
    total_h = 5075
    stickerprint_img = image_for_rendering(model, w=total_w, h=total_h)
    r = Renderer.make(stickerprint_img, geom_s, style)
    # fsUM,MM,LM:
    y = 0
    y += o_y2 + o_a
    x_off = 750
    x_left = geom.oX + x_off
    slide_h = geom_s.slide_h
    stator_h = geom_s.stator_h
    transcribe(sliderule_img, stickerprint_img, x_left, geom.oY, scale_w, stator_h, o_x2, y)
    extend(stickerprint_img, geom_s, y + stator_h - 1, BleedDir.DOWN, ext)
    r.draw_corners(o_x2, y - o_a, o_x2 + scale_w, y + stator_h)
    y += stator_h + o_a
    transcribe(sliderule_img, stickerprint_img, x_left, geom.oY + stator_h + 1, scale_w, slide_h, o_x2, y)
    extend(stickerprint_img, geom_s, y + 1, BleedDir.UP, ext)
    extend(stickerprint_img, geom_s, y + slide_h - 1, BleedDir.DOWN, ext)
    r.draw_corners(o_x2, y, o_x2 + scale_w, y + slide_h)
    y += slide_h + o_a
    transcribe(sliderule_img, stickerprint_img, x_left, geom.oY + geom.side_h - stator_h, scale_w, stator_h, o_x2, y)
    extend(stickerprint_img, geom_s, y + 1, BleedDir.UP, ext)
    extend(stickerprint_img, geom_s, y + stator_h - 1, BleedDir.DOWN, ext)
    r.draw_corners(o_x2, y, o_x2 + scale_w, y + stator_h + o_a)
    # bsUM,MM,LM:
    y += stator_h + o_a + o_a + o_a
    y_start = geom.oY + geom.side_h + geom.oY
    transcribe(sliderule_img, stickerprint_img, x_left, y_start, scale_w, stator_h, o_x2, y)
    extend(stickerprint_img, geom_s, y + stator_h - 1, BleedDir.DOWN, ext)
    r.draw_corners(o_x2, y - o_a, o_x2 + scale_w, y + stator_h)
    y += stator_h + o_a
    transcribe(sliderule_img, stickerprint_img, x_left, y_start + stator_h + 1 - 3, scale_w, slide_h, o_x2, y)
    extend(stickerprint_img, geom_s, y + 1, BleedDir.UP, ext)
    extend(stickerprint_img, geom_s, y + slide_h - 1, BleedDir.DOWN, ext)
    r.draw_corners(o_x2, y, o_x2 + scale_w, y + slide_h)
    y += slide_h + o_a
    transcribe(sliderule_img, stickerprint_img, x_left, y_start + geom_s.side_h - stator_h, scale_w, stator_h, o_x2, y)
    extend(stickerprint_img, geom_s, y + 1, BleedDir.UP, ext)
    extend(stickerprint_img, geom_s, y + stator_h - 1, BleedDir.DOWN, ext)
    y_bottom = y + stator_h + o_a
    r.draw_corners(o_x2, y, o_x2 + scale_w, y_bottom)
    y_b = y_bottom + 20
    box_w = 510
    boxes = [
        [o_a, y_b,
         box_w + o_a, stator_h + o_a],
        [box_w + 3 * o_a, y_b,
         x_off + o_a, slide_h],
        [box_w + x_off + 5 * o_a, y_b,
         x_off + o_a, stator_h + o_a]
    ]
    box_x_mirror = 6.5 * o_a + box_w + 2 * x_off
    for box in boxes:
        (x0, y0, dx, dy) = box
        r.draw_box(x0, y0, dx, dy, Colors.CUT)
        r.draw_box(x0, y0 + slide_h + o_a, dx, dy, Colors.CUT)

        x0 = round(2 * box_x_mirror - x0 - dx)

        r.draw_box(x0, y0, dx, dy, Colors.CUT)
        r.draw_box(x0, y0 + slide_h + o_a, dx, dy, Colors.CUT)
    points = [
        [2 * o_a + 120, y_b + o_a + scale_h],
        [6 * o_a + box_w + x_off + 2 * scale_h, y_b + scale_h],
        [6 * o_a + box_w + x_off + scale_h, y_b + 2 * scale_h],

        [2 * o_a + 120, y_b + slide_h + o_a + scale_h],
        [6 * o_a + box_w + x_off + scale_h, y_b + 640 + o_a + o_a + 2 * scale_h],
        [6 * o_a + box_w + x_off + 2 * scale_h, y_b + 640 + o_a + o_a + scale_h]
    ]
    hole_r = 34  # (2.5mm diameter screw holes) = math.ceil(0.25 * Geometry.PixelsPerCM / 2)
    for (p_x, p_y) in points:
        r.draw_circle(p_x, p_y, hole_r, Colors.CUT)
        p_x_mirror = round(2 * box_x_mirror - p_x)
        r.draw_circle(p_x_mirror, p_y, hole_r, Colors.CUT)
    return stickerprint_img


def render_diagnostic_mode(model: Model, all_scales=False):
    """
    Diagnostic mode, rendering scales independently.
    Works as a test of tick marks, labeling, and layout. Also, regressions.
    If you're reading this, you're a real one
    +5 brownie points to you
    """
    scale_h = Geometry.SH
    k = 120 + scale_h
    is_demo = model == Models.Demo
    layout = model.layout
    style = model.style
    upper = Align.UPPER
    sh_with_margins = scale_h + (40 if is_demo else 10)
    scale_names = ['A', 'B', 'C', 'D', 'K', 'R1', 'R2', 'CI', 'DI', 'CF', 'DF', 'CIF', 'L', 'S', 'T', 'ST']
    for sc_name in keys_of(Scales) if all_scales else layout.sc_keys_in_order():
        if sc_name not in scale_names:
            scale_names.append(sc_name)
    total_h = k + (len(scale_names) + 1) * sh_with_margins + scale_h
    geom_d = Geometry(
        (6500, total_h),
        (250, 250),  # remove y-margin to stack scales
        (Geometry.SL, scale_h),
        Geometry.DEFAULT_TICK_WH,
        480
    )
    diagnostic_img = image_for_rendering(model, w=geom_d.total_w, h=total_h)
    r = Renderer.make(diagnostic_img, geom_d, style)
    title_x = geom_d.midpoint_x - geom_d.li
    title = 'Diagnostic Test Print of Available Scales'
    r.draw_sym_al(title, 50, style.fg, 0, title_x, 0, style.font_for(FontSize.TITLE), upper)
    r.draw_sym_al(' '.join(scale_names), 200, style.fg, 0, title_x, 0, style.font_for(FontSize.SUBTITLE), upper)
    for n, sc_name in enumerate(scale_names):
        sc = getattr(Scales, sc_name, None) or getattr(Rulers, sc_name, None)
        al = Align.LOWER if is_demo else layout.scale_al(sc, Side.FRONT, RulePart.SLIDE)
        y_off = k + (n + 1) * sh_with_margins
        if isinstance(sc, Ruler):
            sc.pat(r, y_off, al)
        elif isinstance(sc, Scale):
            gen_scale(r, y_off, sc, al)
    return diagnostic_img


if __name__ == '__main__':
    main()
