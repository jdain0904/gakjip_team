"""Shared UI helpers for all screens."""
import math
import os
import pygame
from constants import WHITE, GRAY, DIM


_fonts: dict[str, pygame.font.Font] = {}

# Bundled Korean font (NAVER Nanum Gothic, SIL OFL 1.1 — see LICENSE file
# alongside it). Loading this directly guarantees correct Hangul rendering
# on every machine the game ships to, regardless of which system fonts (if
# any) happen to be installed — the previous approach relied on guessing an
# installed font name, which silently produced tofu/blank glyphs on systems
# without one of those specific fonts.
_BUNDLED_FONT = os.path.join(os.path.dirname(__file__), "assets", "fonts", "NanumGothic.ttf")


def _find_fallback_font_path() -> str | None:
    """Only used if the bundled font file is somehow missing.

    pygame.font.SysFont() never fails — for an unknown name it silently
    substitutes a Latin-only default — so this resolves each candidate
    through match_font() (which returns a real file path or None) and loads
    that exact file directly, rather than asking SysFont to re-resolve the
    name itself through a possibly different matching path.
    """
    candidates = ["malgungothic", "malgun gothic", "applegothic", "nanumgothic",
                  "gulim", "dotum", "notosanskr", "notosanscjkkr",
                  "wenquanyizenhei", "unifont", "dejavusans", "arial"]
    for name in candidates:
        path = pygame.font.match_font(name)
        if path:
            return path
    return None


def init_fonts():
    sizes = {"title": 44, "large": 32, "sub": 22,
             "normal": 18, "small": 15, "tiny": 12}
    path = _BUNDLED_FONT if os.path.exists(_BUNDLED_FONT) else _find_fallback_font_path()
    for key, sz in sizes.items():
        _fonts[key] = pygame.font.Font(path, sz) if path else pygame.font.Font(None, sz + 4)


def font(key: str) -> pygame.font.Font:
    return _fonts.get(key, _fonts.get("normal"))


def draw_text(surf, text, fkey, color, x, y, anchor="topleft"):
    f = font(fkey)
    img = f.render(str(text), True, color)
    r = img.get_rect(**{anchor: (x, y)})
    surf.blit(img, r)
    return r


def draw_suit_icon(surf, suit_value: str, cx: int, cy: int, size: int, color):
    """Draw a playing card suit symbol as shapes (no font required)."""
    r = max(3, size // 2)
    if suit_value == '♥':
        h = max(2, r // 2)
        pygame.draw.circle(surf, color, (cx - h, cy - h // 2), h)
        pygame.draw.circle(surf, color, (cx + h, cy - h // 2), h)
        pygame.draw.polygon(surf, color, [(cx - r, cy), (cx + r, cy), (cx, cy + r)])
    elif suit_value == '♦':
        pygame.draw.polygon(surf, color,
                            [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)])
    elif suit_value == '♠':
        h = max(2, r // 2)
        pygame.draw.circle(surf, color, (cx - h, cy + h // 2 - r // 2), h)
        pygame.draw.circle(surf, color, (cx + h, cy + h // 2 - r // 2), h)
        pygame.draw.polygon(surf, color,
                            [(cx - r, cy), (cx + r, cy), (cx, cy - r + 2)])
        stem_w = max(1, r // 3)
        pygame.draw.rect(surf, color,
                         (cx - stem_w, cy + r // 3, stem_w * 2, r // 2))
        pygame.draw.line(surf, color,
                         (cx - r // 2, cy + r // 3 + r // 2),
                         (cx + r // 2, cy + r // 3 + r // 2), max(1, r // 4))
    elif suit_value == '♣':
        cr = max(2, r // 2 - 1)
        pygame.draw.circle(surf, color, (cx, cy - cr + 1), cr)
        pygame.draw.circle(surf, color, (cx - cr, cy + cr // 2), cr)
        pygame.draw.circle(surf, color, (cx + cr, cy + cr // 2), cr)
        stem_w = max(1, cr // 2)
        pygame.draw.rect(surf, color, (cx - stem_w, cy + cr, stem_w * 2, cr))
        pygame.draw.line(surf, color,
                         (cx - cr, cy + cr * 2),
                         (cx + cr, cy + cr * 2), max(1, stem_w))


def rounded_rect(surf, color, rect, r=10, border=0, bc=None):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if border:
        pygame.draw.rect(surf, bc or WHITE, rect, border, border_radius=r)


def vertical_gradient(w: int, h: int, top, bottom) -> pygame.Surface:
    """Build a Surface filled with a smooth top-to-bottom color gradient."""
    surf = pygame.Surface((max(1, w), max(1, h)))
    h = max(1, h)
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(surf, col, (0, y), (w, y))
    return surf


def radial_vignette(w: int, h: int, max_alpha: int = 130, steps: int = 28) -> pygame.Surface:
    """Build a transparent Surface that darkens smoothly toward the edges."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w / 2, h / 2
    max_r = math.hypot(cx, cy)
    for i in range(steps):
        r = max_r * (i + 1) / steps
        a = int(max_alpha * (i / (steps - 1)) ** 1.5) if steps > 1 else max_alpha
        ring_w = int(max_r / steps) + 2
        pygame.draw.circle(surf, (0, 0, 0, a), (cx, cy), int(r), ring_w)
    return surf


class Button:
    """A clickable rounded rectangle with a label — every screen's mouse
    interaction (menu choices, play/end-turn, target picks, ...) is built
    from these; draw() renders it and clicked() reports a left-click hit."""
    def __init__(self, rect, label, color=None, radius=9, fkey="small",
                 text_color=None):
        from constants import ACCENT
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color or ACCENT
        self.radius = radius
        self.fkey = fkey
        self.text_color = text_color or WHITE
        self.enabled = True

    def draw(self, surf, hovered=False):
        c = self.color
        if not self.enabled:
            c = DIM
        elif hovered:
            c = tuple(min(255, v + 28) for v in c)
        rounded_rect(surf, c, self.rect, self.radius)
        pygame.draw.rect(surf, (*WHITE[:3], 60), self.rect, 1,
                         border_radius=self.radius)
        col = GRAY if not self.enabled else self.text_color
        draw_text(surf, self.label, self.fkey, col,
                  self.rect.centerx, self.rect.centery, "center")

    def is_hovered(self, pos):
        return self.rect.collidepoint(pos)

    def clicked(self, event, pos):
        return (self.enabled
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(pos))
