"""Shared UI helpers for all screens."""
import pygame
from constants import WHITE, GRAY, DIM


_fonts: dict[str, pygame.font.Font] = {}


def init_fonts():
    candidates = ["malgungothic", "malgun gothic", "nanumgothic", "gulim",
                  "notosanskr", "freesansbold", "dejavusans", "arial"]
    sizes = {"title": 44, "large": 32, "sub": 22,
             "normal": 18, "small": 15, "tiny": 12}
    for key, sz in sizes.items():
        loaded = False
        for name in candidates:
            try:
                f = pygame.font.SysFont(name, sz)
                if f:
                    _fonts[key] = f
                    loaded = True
                    break
            except Exception:
                pass
        if not loaded:
            _fonts[key] = pygame.font.Font(None, sz + 4)


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


class Button:
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
