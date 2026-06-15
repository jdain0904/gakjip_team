"""Card rendering matching original Bang! card art style.

Three frame types:
  - Parchment (brown): play cards, role cards
  - Character: green dotted border, cream bg, sepia art area
  - Blue: light-blue bg, cornflower border (equipment/blue cards)

Image replacement:
  Place card images in bang/assets/cards/ — see README.txt for filenames.
  When an image exists it is drawn directly (scaled to fit); otherwise the
  programmatic fallback is used.
"""
from __future__ import annotations
import os
import pygame
import math
from cards import Card, CardType
from roles import Role
from characters import CharacterType, CHARACTERS

# ── Asset loading (lazy, cached) ─────────────────────────────────────────────
_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets", "cards")
_img_cache: dict[str, pygame.Surface | None] = {}

def _load(rel_path: str) -> pygame.Surface | None:
    """Load image relative to assets/cards/; returns None if missing."""
    if rel_path in _img_cache:
        return _img_cache[rel_path]
    full = os.path.join(_ASSET_DIR, rel_path)
    if os.path.exists(full):
        try:
            img = pygame.image.load(full).convert_alpha()
            _img_cache[rel_path] = img
            return img
        except Exception:
            pass
    _img_cache[rel_path] = None
    return None

def _blit_card_image(surf: pygame.Surface, img: pygame.Surface,
                     rect: pygame.Rect):
    """Scale img to rect and draw with rounded-corner clip."""
    scaled = pygame.transform.smoothscale(img, (rect.w, rect.h))
    surf.blit(scaled, rect.topleft)

# Filename maps
_GAME_CARD_FILE = {
    CardType.BANG:        "bang.png",
    CardType.MISSED:      "missed.png",
    CardType.BEER:        "beer.png",
    CardType.STAGECOACH:  "stagecoach.png",
    CardType.WELLS_FARGO: "wells_fargo.png",
    CardType.CAT_BALOU:   "cat_balou.png",
    CardType.PANIC:       "panic.png",
    CardType.INDIANS:     "indians.png",
    CardType.GATLING:     "gatling.png",
    CardType.SALOON:      "saloon.png",
    CardType.GEN_STORE:   "gen_store.png",
    CardType.DUEL:        "duel.png",
    CardType.VOLCANIC:    "volcanic.png",
    CardType.SCHOFIELD:   "schofield.png",
    CardType.REMINGTON:   "remington.png",
    CardType.CARABINE:    "carabine.png",
    CardType.WINCHESTER:  "winchester.png",
    CardType.BARREL:      "barrel.png",
    CardType.SCOPE:       "scope.png",
    CardType.MUSTANG:     "mustang.png",
    CardType.JAIL:        "jail.png",
    CardType.DYNAMITE:    "dynamite.png",
}
_ROLE_FILE = {
    Role.SHERIFF:  "sheriff.png",
    Role.DEPUTY:   "deputy.png",
    Role.OUTLAW:   "outlaw.png",
    Role.RENEGADE: "renegade.png",
}
_CHAR_FILE = {
    CharacterType.BART_CASSIDY:   "bart_cassidy.png",
    CharacterType.BLACK_JACK:     "black_jack.png",
    CharacterType.CALAMITY_JANET: "calamity_janet.png",
    CharacterType.EL_GRINGO:      "el_gringo.png",
    CharacterType.JESSE_JONES:    "jesse_jones.png",
    CharacterType.JOURDONNAIS:    "jourdonnais.png",
    CharacterType.KIT_CARLSON:    "kit_carlson.png",
    CharacterType.LUCKY_DUKE:     "lucky_duke.png",
    CharacterType.PAUL_REGRET:    "paul_regret.png",
    CharacterType.PEDRO_RAMIREZ:  "pedro_ramirez.png",
    CharacterType.ROSE_DOOLAN:    "rose_doolan.png",
    CharacterType.SID_KETCHUM:    "sid_ketchum.png",
    CharacterType.SLAB_KILLER:    "slab_killer.png",
    CharacterType.SUZY_LAFAYETTE: "suzy_lafayette.png",
    CharacterType.VULTURE_SAM:    "vulture_sam.png",
    CharacterType.WILLY_KID:      "willy_kid.png",
}

# ── Palette ──────────────────────────────────────────────────────────────────
PARCHMENT     = (235, 215, 175)
PARCHMENT_LGT = (248, 236, 204)
PARCHMENT_DRK = (195, 168, 110)
BORDER_TAN    = (192, 150,  72)
BORDER_DRK    = (130,  95,  30)

CHAR_BG       = (252, 248, 240)
CHAR_SEPIA    = (218, 195, 145)
CHAR_GREEN    = ( 88, 135,  68)
CHAR_GREEN_DRK= ( 55,  95,  40)
CHAR_DOT      = (252, 250, 245)
BULLET_Y      = (220, 178,  38)
BULLET_DRK    = (145, 112,  18)

BLUE_BG       = (224, 238, 255)
BLUE_BORDER   = ( 95, 145, 210)
BLUE_DRK      = ( 60, 100, 175)

TEXT_INK      = ( 30,  18,   6)
TEXT_MID      = ( 80,  60,  35)
TEXT_BLUE_INK = ( 35,  60, 145)

ROLE_FILL = {
    Role.SHERIFF:  (215, 178,  52),
    Role.DEPUTY:   ( 80, 122, 205),
    Role.OUTLAW:   (175,  48,  38),
    Role.RENEGADE: (105,  62, 158),
}
ROLE_NAME_KO = {
    Role.SHERIFF:  "보안관",
    Role.DEPUTY:   "부관",
    Role.OUTLAW:   "무법자",
    Role.RENEGADE: "배신자",
}
ROLE_OBJ_KO = {
    Role.SHERIFF:  "모든 무법자와 배신자를 처치하라",
    Role.DEPUTY:   "보안관을 보호하고 적을 처치하라",
    Role.OUTLAW:   "보안관을 처치하라",
    Role.RENEGADE: "마지막 한 명이 되어라",
}


# ── Tiny draw helpers ─────────────────────────────────────────────────────────

def _shadow(surf: pygame.Surface, rect: pygame.Rect, radius=10):
    sh = pygame.Surface((rect.w + 6, rect.h + 6), pygame.SRCALPHA)
    pygame.draw.rect(sh, (10, 6, 2, 100), sh.get_rect(), border_radius=radius + 2)
    surf.blit(sh, (rect.x + 3, rect.y + 4))


def _parchment_edges(surf: pygame.Surface, rect: pygame.Rect, radius: int):
    """Darken edges for aged parchment look."""
    w, h = rect.w, rect.h
    ov = pygame.Surface((w, h), pygame.SRCALPHA)
    corners = [(0, 0), (w, 0), (0, h), (w, h)]
    for cx, cy in corners:
        for r in range(min(w, h) // 2, 0, -8):
            a = max(0, 28 - r // 2)
            pygame.draw.circle(ov, (80, 50, 10, a), (cx, cy), r)
    surf.blit(ov, rect.topleft)


def _fit_text(surf, text, fkey, color, cx, y, max_w, anchor="center"):
    from ui_utils import font as get_font, draw_text
    f = get_font(fkey)
    if f.size(text)[0] > max_w:
        # try smaller
        for key in ("small", "tiny"):
            f2 = get_font(key)
            if f2.size(text)[0] <= max_w:
                return draw_text(surf, text, key, color, cx, y, anchor)
        text = text[:max(1, len(text) - 2)] + "…"
    return draw_text(surf, text, fkey, color, cx, y, anchor)


# ── Bullet (HP) icons ─────────────────────────────────────────────────────────

def draw_bullets(surf: pygame.Surface, n: int, x: int, y: int, size=10):
    """Draw n stacked bullet icons (like character cards), top-right corner."""
    bw = size
    bh = int(size * 2.5)
    gap = 3
    total_w = n * (bw + gap) - gap
    ox = x - total_w
    for i in range(n):
        bx = ox + i * (bw + gap)
        # Bullet body
        body = pygame.Rect(bx, y + size // 2, bw, bh - size // 2)
        pygame.draw.rect(surf, BULLET_Y, body, border_radius=3)
        pygame.draw.rect(surf, BULLET_DRK, body, 1, border_radius=3)
        # Bullet tip (triangle / rounded top)
        pts = [(bx, y + size // 2),
               (bx + bw, y + size // 2),
               (bx + bw // 2, y)]
        pygame.draw.polygon(surf, BULLET_Y, pts)
        pygame.draw.polygon(surf, BULLET_DRK, pts, 1)
        # Rim line
        pygame.draw.line(surf, BULLET_DRK, (bx, y + size // 2 + 2),
                         (bx + bw, y + size // 2 + 2))


# ── Frame drawers ─────────────────────────────────────────────────────────────

def draw_parchment_frame(surf: pygame.Surface, rect: pygame.Rect, inner_pad=4):
    """Draw aged parchment frame (brown play + role cards)."""
    r = 10
    _shadow(surf, rect, r)
    # Outer border (tan)
    outer = rect.inflate(4, 4)
    pygame.draw.rect(surf, BORDER_TAN, outer, border_radius=r + 2)
    pygame.draw.rect(surf, BORDER_DRK, outer, 1, border_radius=r + 2)
    # Parchment fill
    pygame.draw.rect(surf, PARCHMENT, rect, border_radius=r)
    _parchment_edges(surf, rect, r)
    # Inner border line
    inner = rect.inflate(-inner_pad * 2, -inner_pad * 2)
    pygame.draw.rect(surf, BORDER_TAN, inner, 1, border_radius=max(4, r - inner_pad))


def draw_blue_frame(surf: pygame.Surface, rect: pygame.Rect):
    """Draw blue equipment card frame."""
    r = 10
    _shadow(surf, rect, r)
    # Outer border
    outer = rect.inflate(4, 4)
    pygame.draw.rect(surf, BLUE_DRK, outer, border_radius=r + 2)
    # Blue fill
    pygame.draw.rect(surf, BLUE_BG, rect, border_radius=r)
    # Blue border inner line
    pygame.draw.rect(surf, BLUE_BORDER, rect, 4, border_radius=r)


def draw_character_frame(surf: pygame.Surface, rect: pygame.Rect):
    """Draw character card frame (green dotted border, cream bg)."""
    r = 12
    _shadow(surf, rect, r)
    # Green outer border
    pygame.draw.rect(surf, CHAR_GREEN_DRK, rect.inflate(6, 6), border_radius=r + 3)
    pygame.draw.rect(surf, CHAR_GREEN, rect.inflate(4, 4), border_radius=r + 2)
    # Cream background
    pygame.draw.rect(surf, CHAR_BG, rect, border_radius=r)
    # White dots along inner edge of green border
    x, y, w, h = rect
    dot_r = 4
    perimeter = 2 * (w + h)
    n_dots = perimeter // 22
    for i in range(n_dots):
        t = i / n_dots
        if t < 0.25:
            dx = x + t * 4 * w
            dy = y + dot_r + 2
        elif t < 0.5:
            dx = x + w - dot_r - 2
            dy = y + (t - 0.25) * 4 * h
        elif t < 0.75:
            dx = x + w - (t - 0.5) * 4 * w
            dy = y + h - dot_r - 2
        else:
            dx = x + dot_r + 2
            dy = y + h - (t - 0.75) * 4 * h
        pygame.draw.circle(surf, CHAR_DOT, (int(dx), int(dy)), dot_r)


# ── ROLE CARD ─────────────────────────────────────────────────────────────────

def _draw_sheriff_badge(surf, cx, cy, r):
    gold = (215, 182, 58)
    tan  = (188, 148, 60)
    dark = (100,  72, 18)
    # Hexagram (two triangles)
    for angle_off in (0, math.pi):
        pts = []
        for i in range(3):
            a = angle_off + math.pi * 2 / 3 * i - math.pi / 2
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        pygame.draw.polygon(surf, gold, pts)
        pygame.draw.polygon(surf, dark, pts, 2)
    pygame.draw.circle(surf, tan, (cx, cy), int(r * 0.55))
    pygame.draw.circle(surf, dark, (cx, cy), int(r * 0.55), 2)


def _draw_deputy_badge(surf, cx, cy, r):
    cream = (228, 215, 165)
    dark  = (100,  72, 18)
    pts = []
    for i in range(5):
        a = math.pi * 2 / 5 * i - math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pygame.draw.polygon(surf, cream, pts)
    pygame.draw.polygon(surf, dark, pts, 2)
    pygame.draw.circle(surf, (245, 235, 195), (cx, cy), int(r * 0.45))
    pygame.draw.circle(surf, dark, (cx, cy), int(r * 0.45), 2)


def _draw_outlaw_silhouette(surf, cx, cy, h):
    black = (30, 20, 10)
    # Hat brim
    pygame.draw.ellipse(surf, black, (cx - 28, cy - h // 2 + 12, 56, 14))
    # Hat crown
    pygame.draw.rect(surf, black, (cx - 18, cy - h // 2 - 10, 36, 26), border_radius=4)
    # Head
    pygame.draw.ellipse(surf, black, (cx - 16, cy - h // 2 + 20, 32, 30))
    # Body (coat)
    pts = [(cx - 22, cy - h // 2 + 48),
           (cx + 22, cy - h // 2 + 48),
           (cx + 28, cy + h // 2),
           (cx - 28, cy + h // 2)]
    pygame.draw.polygon(surf, black, pts)


def _draw_renegade_hat(surf, cx, cy, r):
    black = (30, 20, 10)
    # Hat brim
    pygame.draw.ellipse(surf, black, (cx - r, cy + r // 4, r * 2, r // 2))
    # Crown
    pts = [(cx - int(r * 0.6), cy + r // 4),
           (cx + int(r * 0.6), cy + r // 4),
           (cx + int(r * 0.4), cy - r),
           (cx - int(r * 0.4), cy - r)]
    pygame.draw.polygon(surf, black, pts)
    # Hat band
    pygame.draw.line(surf, (80, 60, 20),
                     (cx - int(r * 0.6), cy - int(r * 0.15)),
                     (cx + int(r * 0.6), cy - int(r * 0.15)), 4)
    # Face outline (simple oval)
    pygame.draw.ellipse(surf, (160, 130, 90),
                        (cx - int(r * 0.45), cy + r // 4 - int(r * 0.9),
                         int(r * 0.9), int(r * 1.1)))


def draw_role_card(surf: pygame.Surface, role: Role, rect: pygame.Rect):
    from ui_utils import draw_text, font as get_font
    # ── Image override ────────────────────────────────────────────────────
    img = _load(os.path.join("roles", _ROLE_FILE[role]))
    if img:
        _blit_card_image(surf, img, rect)
        return
    # ── Programmatic fallback ─────────────────────────────────────────────
    draw_parchment_frame(surf, rect)
    x, y, w, h = rect

    # Title banner area
    title_h = int(h * 0.22)
    title_bg = pygame.Rect(x + 6, y + 6, w - 12, title_h)
    pygame.draw.rect(surf, PARCHMENT_DRK, title_bg, border_radius=6)
    pygame.draw.rect(surf, BORDER_TAN, title_bg, 1, border_radius=6)
    name_ko = ROLE_NAME_KO[role]
    draw_text(surf, name_ko, "large", TEXT_INK, rect.centerx, y + 16, "center")

    # Illustration area
    ill_y   = y + title_h + 10
    ill_h   = int(h * 0.40)
    ill_rect = pygame.Rect(x + 12, ill_y, w - 24, ill_h)
    pygame.draw.rect(surf, PARCHMENT_LGT, ill_rect, border_radius=6)
    pygame.draw.rect(surf, BORDER_TAN, ill_rect, 1, border_radius=6)

    icx = ill_rect.centerx
    icy = ill_rect.centery
    icon_r = min(ill_rect.w, ill_rect.h) // 2 - 8

    if role == Role.SHERIFF:
        _draw_sheriff_badge(surf, icx, icy, icon_r)
    elif role == Role.DEPUTY:
        _draw_deputy_badge(surf, icx, icy, icon_r)
    elif role == Role.OUTLAW:
        _draw_outlaw_silhouette(surf, icx, icy, ill_h - 16)
    else:  # RENEGADE
        _draw_renegade_hat(surf, icx, icy, icon_r)

    # Objective text
    obj_y = ill_y + ill_h + 10
    obj = ROLE_OBJ_KO[role]
    fnt = get_font("small")
    words = obj.split()
    line, lines = "", []
    for w_tok in words:
        test = (line + " " + w_tok).strip()
        if fnt.size(test)[0] > rect.w - 28:
            lines.append(line)
            line = w_tok
        else:
            line = test
    if line:
        lines.append(line)
    for li, txt in enumerate(lines):
        draw_text(surf, txt, "small", TEXT_MID,
                  rect.centerx, obj_y + li * 18, "center")

    # Role colour accent bar at bottom
    bar_h = 18
    bar = pygame.Rect(x + 8, y + h - bar_h - 6, w - 16, bar_h)
    fill = ROLE_FILL[role]
    pygame.draw.rect(surf, fill, bar, border_radius=6)
    draw_text(surf, name_ko, "tiny", (255, 255, 255),
              bar.centerx, bar.centery, "center")


# ── CHARACTER CARD ────────────────────────────────────────────────────────────

# Simple icons for each character (drawn in sepia area)
def _draw_char_icon(surf, char: CharacterType, cx, cy, r):
    """Draw a simple representative icon for a character."""
    dark   = (80, 55, 20)
    sepia2 = (170, 138, 85)
    gold   = (210, 172, 45)

    if char == CharacterType.BART_CASSIDY:
        # Cards flying out
        for i, off in enumerate((-15, 0, 15)):
            cr = pygame.Rect(cx + off - 8, cy - r // 2 - 10, 18, 26)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=3)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=3)
    elif char == CharacterType.BLACK_JACK:
        # Card being revealed
        cr = pygame.Rect(cx - 14, cy - 20, 28, 38)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=3)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=3)
        draw_heart(surf, cx, cy + 2, 10)
    elif char == CharacterType.CALAMITY_JANET:
        # BANG! ↔ Missed! arrows
        pygame.draw.line(surf, dark, (cx - 22, cy - 8), (cx + 22, cy - 8), 2)
        pygame.draw.polygon(surf, dark, [(cx + 22, cy - 8),
                                         (cx + 14, cy - 14), (cx + 14, cy - 2)])
        pygame.draw.line(surf, dark, (cx + 22, cy + 8), (cx - 22, cy + 8), 2)
        pygame.draw.polygon(surf, dark, [(cx - 22, cy + 8),
                                         (cx - 14, cy + 14), (cx - 14, cy + 2)])
    elif char == CharacterType.EL_GRINGO:
        # Hand stealing a card
        cr = pygame.Rect(cx - 10, cy - 18, 20, 28)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
        # Arrow pointing to card
        pygame.draw.line(surf, dark, (cx - 28, cy), (cx - 14, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx - 14, cy),
                                         (cx - 20, cy - 5), (cx - 20, cy + 5)])
    elif char in (CharacterType.JESSE_JONES, CharacterType.PEDRO_RAMIREZ):
        # Arrow from discard/player to hand
        pygame.draw.line(surf, dark, (cx - 26, cy), (cx, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx, cy), (cx - 8, cy - 5), (cx - 8, cy + 5)])
        cr = pygame.Rect(cx + 4, cy - 15, 20, 28)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.JOURDONNAIS:
        # Barrel
        pygame.draw.ellipse(surf, sepia2, (cx - 18, cy - r + 6, 36, 16))
        pygame.draw.rect(surf, sepia2, (cx - 18, cy - r + 14, 36, 28))
        pygame.draw.ellipse(surf, sepia2, (cx - 18, cy - r + 36, 36, 14))
        for ly in (cy - r + 20, cy - r + 28):
            pygame.draw.line(surf, dark, (cx - 18, ly), (cx + 18, ly), 1)
        pygame.draw.rect(surf, dark, (cx - 18, cy - r + 14, 36, 28), 1)
    elif char == CharacterType.KIT_CARLSON:
        # 3 cards being reviewed → pick 2
        for i, off in enumerate((-22, 0, 22)):
            cr = pygame.Rect(cx + off - 9, cy - 20, 18, 26)
            col = gold if i < 2 else PARCHMENT_DRK
            pygame.draw.rect(surf, col, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.LUCKY_DUKE:
        # Two flipped cards
        for off in (-12, 8):
            cr = pygame.Rect(cx + off, cy - 20, 18, 26)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.PAUL_REGRET:
        # Distance +1 (horse/figure pushed away)
        pygame.draw.circle(surf, sepia2, (cx - 16, cy), 12)
        pygame.draw.circle(surf, dark, (cx - 16, cy), 12, 1)
        draw_text_tiny(surf, "+1", dark, cx + 8, cy - 7)
    elif char == CharacterType.ROSE_DOOLAN:
        # Scope/telescope
        pygame.draw.rect(surf, sepia2, (cx - 22, cy - 6, 44, 10), border_radius=4)
        pygame.draw.circle(surf, dark, (cx + 22, cy), 9, 2)
        pygame.draw.rect(surf, dark, (cx - 22, cy - 6, 44, 10), 1, border_radius=4)
    elif char == CharacterType.SID_KETCHUM:
        # 2 cards → HP heart
        for i, off in enumerate((-14, 0)):
            cr = pygame.Rect(cx + off, cy - 20, 16, 22)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
        pygame.draw.line(surf, dark, (cx + 18, cy), (cx + 26, cy), 2)
        draw_heart(surf, cx + 35, cy, 9)
    elif char == CharacterType.SLAB_KILLER:
        # 2 Missed! cards needed
        for i, off in enumerate((-14, 4)):
            cr = pygame.Rect(cx + off, cy - 15, 16, 22)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
            draw_text_tiny(surf, "M", dark, cx + off + 8, cy - 8)
    elif char == CharacterType.SUZY_LAFAYETTE:
        # Empty hand → draw card
        draw_text_tiny(surf, "0장", dark, cx - 18, cy - 10)
        pygame.draw.line(surf, dark, (cx - 5, cy), (cx + 5, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx + 5, cy), (cx - 1, cy - 5), (cx - 1, cy + 5)])
        cr = pygame.Rect(cx + 8, cy - 14, 16, 22)
        pygame.draw.rect(surf, gold, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.VULTURE_SAM:
        # All cards from eliminated player
        for i in range(3):
            cr = pygame.Rect(cx - 16 + i * 10, cy - 16 + i * 4, 18, 24)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.WILLY_KID:
        # BANG! × ∞
        draw_text_tiny(surf, "BANG!", dark, cx - 10, cy - 10)
        draw_text_tiny(surf, "× ∞", dark, cx + 2, cy + 2)
    else:
        # Generic gun icon
        pygame.draw.rect(surf, dark, (cx - 22, cy - 6, 30, 10), border_radius=3)
        pygame.draw.rect(surf, dark, (cx + 6, cy - 16, 12, 10), border_radius=2)
        pygame.draw.line(surf, dark, (cx - 22, cy + 4), (cx - 14, cy + 14), 2)


def draw_heart(surf, cx, cy, r):
    """Draw a small heart shape."""
    red = (200, 50, 45)
    pts = []
    for deg in range(0, 360, 8):
        t = math.radians(deg)
        hx = r * (16 * math.sin(t) ** 3) / 16
        hy = -r * (13 * math.cos(t) - 5 * math.cos(2 * t) -
                   2 * math.cos(3 * t) - math.cos(4 * t)) / 16
        pts.append((cx + hx, cy + hy))
    if len(pts) >= 3:
        pygame.draw.polygon(surf, red, pts)


def draw_text_tiny(surf, text, color, x, y):
    """Minimal text draw without importing ui_utils recursively."""
    from ui_utils import draw_text
    draw_text(surf, text, "tiny", color, x, y)


def draw_character_card(surf: pygame.Surface,
                        char: CharacterType,
                        max_hp: int,
                        rect: pygame.Rect):
    from ui_utils import draw_text, font as get_font
    # ── Image override ────────────────────────────────────────────────────
    img = _load(os.path.join("characters", _CHAR_FILE[char]))
    if img:
        _blit_card_image(surf, img, rect)
        return
    # ── Programmatic fallback ─────────────────────────────────────────────
    draw_character_frame(surf, rect)
    x, y, w, h = rect

    info = CHARACTERS[char]

    # Title
    title_y = y + 10
    draw_text(surf, info.name_en.upper(), "sub", TEXT_INK,
              rect.centerx - 20, title_y, "center")

    # HP bullets (top-right)
    draw_bullets(surf, max_hp, x + w - 8, title_y + 2, size=8)

    # Sepia illustration area
    art_y = title_y + 26
    art_h = int(h * 0.42)
    art   = pygame.Rect(x + 10, art_y, w - 20, art_h)
    pygame.draw.rect(surf, CHAR_SEPIA, art, border_radius=6)
    pygame.draw.rect(surf, PARCHMENT_DRK, art, 1, border_radius=6)

    # Character icon in art area
    _draw_char_icon(surf, char, art.centerx, art.centery,
                    min(art.w, art.h) // 2 - 6)

    # Korean name bar
    bar_y = art_y + art_h + 6
    draw_text(surf, info.name_ko, "small", TEXT_INK,
              rect.centerx, bar_y, "center")

    # Description
    desc_y = bar_y + 20
    fnt = get_font("tiny")
    desc = info.desc
    words = desc.split()
    line, lines = "", []
    for tok in words:
        test = (line + " " + tok).strip()
        if fnt.size(test)[0] > w - 20:
            lines.append(line)
            line = tok
        else:
            line = test
    if line:
        lines.append(line)
    for li, txt in enumerate(lines):
        draw_text(surf, txt, "tiny", TEXT_MID,
                  rect.centerx, desc_y + li * 16, "center")


# ── GAME CARD (small, in hand) ────────────────────────────────────────────────

# Simple icons for each card type drawn in the card's art area
def _draw_card_icon(surf, card: Card, cx, cy, r):
    dark  = TEXT_INK
    red   = (190, 45, 38)
    gold  = (210, 172, 45)
    blue  = (60, 105, 185)
    green = (55, 128, 60)

    ct = card.card_type

    if ct == CardType.BANG:
        # Explosion starburst
        for i in range(8):
            a = math.radians(i * 45)
            ex = cx + int(r * 0.85 * math.cos(a))
            ey = cy + int(r * 0.85 * math.sin(a))
            pygame.draw.line(surf, (210, 120, 30), (cx, cy), (ex, ey), 2)
        pygame.draw.circle(surf, (215, 80, 28), (cx, cy), r // 2)
        pygame.draw.circle(surf, dark, (cx, cy), r // 2, 1)

    elif ct == CardType.MISSED:
        # Hat flying off
        pygame.draw.ellipse(surf, (160, 130, 80), (cx - r, cy, r * 2, r // 2))
        pygame.draw.rect(surf, (120, 95, 55), (cx - int(r * 0.6), cy - r, int(r * 1.2), r + 2), border_radius=3)

    elif ct == CardType.BEER:
        # Beer mug
        pygame.draw.rect(surf, (210, 185, 65), (cx - r // 2, cy - int(r * 0.8), r, int(r * 1.6)), border_radius=3)
        pygame.draw.rect(surf, dark, (cx - r // 2, cy - int(r * 0.8), r, int(r * 1.6)), 1, border_radius=3)
        # Handle
        pygame.draw.arc(surf, dark, (cx + r // 2 - 2, cy - r // 4, r // 2, r // 2), 0, math.pi, 2)

    elif ct == CardType.STAGECOACH:
        # Two card icons
        for off in (-10, 6):
            cr = pygame.Rect(cx + off, cy - 14, 14, 20)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)

    elif ct == CardType.WELLS_FARGO:
        # Three card icons
        for off in (-16, -4, 8):
            cr = pygame.Rect(cx + off, cy - 14, 14, 20)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)

    elif ct == CardType.CAT_BALOU:
        # Card with X
        cr = pygame.Rect(cx - 12, cy - 16, 24, 32)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
        pygame.draw.line(surf, red, cr.topleft, cr.bottomright, 2)
        pygame.draw.line(surf, red, cr.topright, cr.bottomleft, 2)

    elif ct == CardType.PANIC:
        # Steal arrow
        pygame.draw.line(surf, dark, (cx - r, cy), (cx + r, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx + r, cy), (cx + r - 7, cy - 5), (cx + r - 7, cy + 5)])
        cr = pygame.Rect(cx + r - 2, cy - 14, 16, 22)
        pygame.draw.rect(surf, gold, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)

    elif ct == CardType.INDIANS:
        # Arrow
        pygame.draw.line(surf, (140, 80, 30), (cx - r, cy), (cx + r, cy), 3)
        pygame.draw.polygon(surf, (140, 80, 30), [(cx + r, cy), (cx + r - 8, cy - 6), (cx + r - 8, cy + 6)])
        # Feathers
        for fy in (-6, 0, 6):
            pygame.draw.line(surf, (160, 100, 40), (cx - r + 4, cy + fy), (cx - r + 12, cy + fy - 4), 1)

    elif ct == CardType.GATLING:
        # X (all players) + gun
        pygame.draw.line(surf, red, (cx - r, cy - r // 2), (cx + r, cy + r // 2), 2)
        pygame.draw.line(surf, red, (cx + r, cy - r // 2), (cx - r, cy + r // 2), 2)

    elif ct == CardType.SALOON:
        # Multiple + signs (group heal)
        for dx, dy in ((-10, -5), (5, -5), (-5, 8)):
            pygame.draw.line(surf, green, (cx + dx - 5, cy + dy), (cx + dx + 5, cy + dy), 2)
            pygame.draw.line(surf, green, (cx + dx, cy + dy - 5), (cx + dx, cy + dy + 5), 2)

    elif ct == CardType.GEN_STORE:
        # Store front shape
        pygame.draw.rect(surf, (180, 145, 85), (cx - r, cy - r // 3, r * 2, int(r * 1.3)), border_radius=2)
        pygame.draw.rect(surf, dark, (cx - r, cy - r // 3, r * 2, int(r * 1.3)), 1, border_radius=2)
        # Awning
        pts = [(cx - r - 3, cy - r // 3), (cx + r + 3, cy - r // 3),
               (cx + r - 4, cy - r), (cx - r + 4, cy - r)]
        pygame.draw.polygon(surf, (160, 50, 40), pts)

    elif ct == CardType.DUEL:
        # Two pistols facing each other
        _draw_mini_gun(surf, cx - 8, cy, dark, flip=False)
        _draw_mini_gun(surf, cx + 8, cy, dark, flip=True)

    elif ct in (CardType.VOLCANIC, CardType.SCHOFIELD,
                CardType.REMINGTON, CardType.CARABINE, CardType.WINCHESTER):
        # Gun silhouette + range circle
        _draw_mini_gun(surf, cx - 4, cy - 2, dark)
        # Range indicator circle
        rn = GUN_RANGE_NUM.get(ct, 1)
        cr2 = pygame.Rect(cx - 10, cy + 6, 20, 20)
        pygame.draw.circle(surf, blue, cr2.center, 10)
        pygame.draw.circle(surf, dark, cr2.center, 10, 1)
        # Crosshair lines
        pygame.draw.line(surf, dark, (cr2.centerx - 7, cr2.centery),
                         (cr2.centerx + 7, cr2.centery), 1)
        pygame.draw.line(surf, dark, (cr2.centerx, cr2.centery - 7),
                         (cr2.centerx, cr2.centery + 7), 1)
        draw_text_tiny(surf, str(rn), (255, 255, 255), cr2.centerx, cr2.centery - 5)

    elif ct == CardType.BARREL:
        # Barrel with heart = dodge
        pygame.draw.ellipse(surf, (165, 115, 55), (cx - 14, cy - r + 4, 28, 12))
        pygame.draw.rect(surf, (145, 95, 40), (cx - 14, cy - r + 10, 28, r - 4), border_radius=2)
        pygame.draw.ellipse(surf, (155, 105, 45), (cx - 14, cy + 2, 28, 10))
        pygame.draw.rect(surf, dark, (cx - 14, cy - r + 10, 28, r - 4), 1, border_radius=2)
        draw_heart(surf, cx + 10, cy, 7)

    elif ct == CardType.SCOPE:
        # Telescope
        pygame.draw.rect(surf, (140, 110, 55), (cx - r, cy - 5, r * 2, 10), border_radius=4)
        pygame.draw.circle(surf, dark, (cx + r, cy), 8, 1)

    elif ct == CardType.MUSTANG:
        # Horse silhouette (very simple)
        pygame.draw.ellipse(surf, dark, (cx - r, cy - 6, r * 2 - 6, 14))
        pygame.draw.ellipse(surf, dark, (cx - r // 2, cy - r, 14, 16))

    elif ct == CardType.JAIL:
        # Bars
        for bx in range(cx - 10, cx + 14, 8):
            pygame.draw.line(surf, dark, (bx, cy - r + 4), (bx, cy + r - 4), 2)
        pygame.draw.line(surf, dark, (cx - 12, cy - r + 4), (cx + 14, cy - r + 4), 2)
        pygame.draw.line(surf, dark, (cx - 12, cy + r - 4), (cx + 14, cy + r - 4), 2)
        draw_heart(surf, cx + 18, cy, 7)

    elif ct == CardType.DYNAMITE:
        # Dynamite stick
        pygame.draw.rect(surf, red, (cx - 8, cy - r + 6, 16, r * 2 - 10), border_radius=3)
        pygame.draw.rect(surf, dark, (cx - 8, cy - r + 6, 16, r * 2 - 10), 1, border_radius=3)
        # Fuse
        pygame.draw.line(surf, (210, 165, 45), (cx, cy - r + 6), (cx + 6, cy - r - 4), 2)


GUN_RANGE_NUM = {
    CardType.VOLCANIC:  1,
    CardType.SCHOFIELD: 2,
    CardType.REMINGTON: 3,
    CardType.CARABINE:  4,
    CardType.WINCHESTER: 5,
}


def _draw_mini_gun(surf, cx, cy, color, flip=False):
    """Draw a very small gun shape."""
    sx = -1 if flip else 1
    pts = [
        (cx + sx * 14, cy - 2),
        (cx + sx * 14, cy + 2),
        (cx - sx * 4,  cy + 2),
        (cx - sx * 6,  cy + 8),
        (cx - sx * 10, cy + 8),
        (cx - sx * 10, cy - 6),
        (cx - sx * 4,  cy - 6),
        (cx - sx * 4,  cy - 2),
    ]
    pygame.draw.polygon(surf, color, pts)


def draw_game_card(surf: pygame.Surface, card: Card,
                   x: int, y: int, w: int, h: int,
                   selected=False, playable=False, discard_mode=False,
                   face_down=False):
    """Draw a styled game card at (x, y) with size (w, h)."""
    from ui_utils import draw_text
    from cards import Suit
    rect = pygame.Rect(x, y, w, h)

    if face_down:
        _shadow(surf, rect, 8)
        pygame.draw.rect(surf, PARCHMENT_DRK, rect, border_radius=8)
        pygame.draw.rect(surf, BORDER_TAN, rect, 3, border_radius=8)
        # Back pattern
        inner = rect.inflate(-10, -10)
        pygame.draw.rect(surf, PARCHMENT, inner, border_radius=6)
        pygame.draw.rect(surf, BORDER_TAN, inner, 1, border_radius=6)
        return

    # ── Image override ────────────────────────────────────────────────────
    img = _load(os.path.join("game", _GAME_CARD_FILE[card.card_type]))
    if img:
        _blit_card_image(surf, img, rect)
        # Draw selection highlight on top of image
        if selected:
            pygame.draw.rect(surf, (255, 215, 0), rect, 3, border_radius=10)
        elif playable:
            pygame.draw.rect(surf, (80, 175, 75), rect, 2, border_radius=10)
        elif discard_mode:
            pygame.draw.rect(surf, (190, 50, 40), rect, 2, border_radius=10)
        return
    # ── Programmatic fallback ─────────────────────────────────────────────

    if card.is_blue:
        draw_blue_frame(surf, rect)
        text_color = TEXT_BLUE_INK
        bg_col = BLUE_BG
    else:
        draw_parchment_frame(surf, rect)
        text_color = TEXT_INK
        bg_col = PARCHMENT

    # Selection/playable highlight
    if selected:
        pygame.draw.rect(surf, (255, 215, 0), rect, 3, border_radius=10)
    elif playable:
        pygame.draw.rect(surf, (80, 175, 75), rect, 2, border_radius=10)
    elif discard_mode:
        pygame.draw.rect(surf, (190, 50, 40), rect, 2, border_radius=10)

    # Suit+value (top-left)
    from cards import Suit
    from ui_utils import draw_suit_icon
    sv_color = (180, 40, 35) if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else TEXT_INK
    val_str = {1: "A", 11: "J", 12: "Q", 13: "K"}.get(card.value, str(card.value))
    draw_suit_icon(surf, card.suit.value, x + 8, y + 6, 10, sv_color)
    draw_text(surf, val_str, "tiny", sv_color, x + 4, y + 14)

    # Title (upper portion)
    name = card.name
    title_y = y + h // 5
    if len(name) > 6:
        # two lines
        mid = name.find(" ", len(name) // 2)
        if mid == -1:
            mid = len(name) // 2
        draw_text(surf, name[:mid], "tiny", text_color, x + w // 2, title_y - 6, "center")
        draw_text(surf, name[mid:].strip(), "tiny", text_color, x + w // 2, title_y + 7, "center")
    else:
        draw_text(surf, name, "small", text_color, x + w // 2, title_y, "center")

    # Card icon / art area (center)
    art_cx = x + w // 2
    art_cy = y + int(h * 0.58)
    icon_r = min(w, h) // 4
    _draw_card_icon(surf, card, art_cx, art_cy, icon_r)

    # Blue equipment: range circle at bottom-center (already drawn in icon)
    # Parchment: type badge at bottom
    if not card.is_blue:
        badge_h = 14
        badge = pygame.Rect(x + 6, y + h - badge_h - 5, w - 12, badge_h)
        pygame.draw.rect(surf, PARCHMENT_DRK, badge, border_radius=3)
        draw_text(surf, "액션", "tiny", TEXT_MID, badge.centerx, badge.centery, "center")
    else:
        badge_h = 14
        badge = pygame.Rect(x + 6, y + h - badge_h - 5, w - 12, badge_h)
        pygame.draw.rect(surf, BLUE_BORDER, badge, border_radius=3)
        draw_text(surf, "장착", "tiny", (255, 255, 255), badge.centerx, badge.centery, "center")
