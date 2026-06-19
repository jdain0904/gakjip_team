"""원작 Bang! 카드의 아트 스타일을 재현하는 카드 렌더링 모듈.

세 가지 프레임 종류:
  - 양피지(Parchment, 갈색): 플레이 카드, 역할 카드
  - 캐릭터: 녹색 점선 테두리, 크림색 배경, 세피아 톤 아트 영역
  - 블루: 라이트블루 배경, 콘플라워색 테두리 (장비/블루 카드)

이미지 교체:
  bang/fwd/ 폴더에 카드 이미지를 넣으면 된다 — 파일명 규칙은 README.txt 참고.
  .webp, .png, .jpg, .jpeg를 지원하며(이 순서로 시도함), 폴더 구조는
  flat(서브폴더 없음) 또는 game/roles/characters 서브폴더 둘 다 동작한다.
  이미지가 존재하면 그것을 (크기에 맞춰 스케일하여) 직접 그리고, 존재하지
  않으면 프로그램으로 그리는 대체 방식을 사용한다.
"""
from __future__ import annotations
import os
import pygame
import math
from cards import Card, CardType
from roles import Role
from characters import CharacterType, CHARACTERS

# ── 에셋 로딩 (지연 로딩, 캐시 사용) ─────────────────────────────────────────────
_ASSET_DIR = os.path.join(os.path.dirname(__file__), "fwd")
_IMG_EXTS = (".webp", ".png", ".jpg", ".jpeg")
_img_cache: dict[str, pygame.Surface | None] = {}

def _load(rel_path: str) -> pygame.Surface | None:
    """fwd/ 기준 상대 경로로 이미지를 로드한다. rel_path에 주어진 확장자와
    무관하게 .webp/.png/.jpg/.jpeg를 모두 시도하며, fwd/가 서브폴더로
    나뉘어 있지 않은 경우를 대비해 flat 조회(파일명만 보고
    game/roles/characters 서브폴더는 무시)로도 한 번 더 시도한다.
    일치하는 파일이 없으면 None을 반환한다."""
    if rel_path in _img_cache:
        return _img_cache[rel_path]

    stem = os.path.splitext(rel_path)[0]
    base = os.path.basename(stem)
    candidates = [stem + ext for ext in _IMG_EXTS]
    candidates += [base + ext for ext in _IMG_EXTS]

    for cand in candidates:
        full = os.path.join(_ASSET_DIR, cand)
        if os.path.exists(full):
            try:
                img = pygame.image.load(full).convert_alpha()
                _img_cache[rel_path] = img
                return img
            except Exception as e:
                # 파일은 존재하지만 pygame이 디코딩하지 못한 경우(예: webp를
                # 지원하지 않는 SDL_image 빌드) — 그냥 폴백으로 넘어가면
                # "파일을 찾을 수 없음"과 똑같이 보이므로, 이 경우는
                # 조용히 넘기지 않고 표면화해서 알려준다.
                print(f"[card_renderer] found {full} but failed to load it: {e}")

    _img_cache[rel_path] = None
    return None

def _blit_card_image(surf: pygame.Surface, img: pygame.Surface,
                     rect: pygame.Rect):
    """img를 rect 크기에 맞게 스케일하고 모서리를 둥글게 잘라 그린다."""
    scaled = pygame.transform.smoothscale(img, (rect.w, rect.h))
    surf.blit(scaled, rect.topleft)

# 파일명 매핑
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

# ── 색상 팔레트 ──────────────────────────────────────────────────────────────────
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


# ── 작은 그리기 헬퍼 함수들 ─────────────────────────────────────────────────────────

def _shadow(surf: pygame.Surface, rect: pygame.Rect, radius=10):
    sh = pygame.Surface((rect.w + 6, rect.h + 6), pygame.SRCALPHA)
    pygame.draw.rect(sh, (10, 6, 2, 100), sh.get_rect(), border_radius=radius + 2)
    surf.blit(sh, (rect.x + 3, rect.y + 4))


def _parchment_edges(surf: pygame.Surface, rect: pygame.Rect, radius: int):
    """오래된 양피지 느낌을 내기 위해 가장자리를 어둡게 처리한다."""
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
        # 더 작은 폰트로 시도
        for key in ("small", "tiny"):
            f2 = get_font(key)
            if f2.size(text)[0] <= max_w:
                return draw_text(surf, text, key, color, cx, y, anchor)
        text = text[:max(1, len(text) - 2)] + "…"
    return draw_text(surf, text, fkey, color, cx, y, anchor)


def _wrap_lines(text: str, fkey: str, max_w: int) -> list[str]:
    """주어진 폰트에서 max_w에 맞도록 텍스트를 그리디(greedy) 방식으로
    단어 단위 줄바꿈하여 여러 줄로 나눈다."""
    from ui_utils import font as get_font
    fnt = get_font(fkey)
    words = text.split()
    line, lines = "", []
    for tok in words:
        test = (line + " " + tok).strip()
        if fnt.size(test)[0] > max_w:
            lines.append(line)
            line = tok
        else:
            line = test
    if line:
        lines.append(line)
    return lines


# ── 총알(HP) 아이콘 ─────────────────────────────────────────────────────────

def draw_bullets(surf: pygame.Surface, n: int, x: int, y: int, size=10):
    """(캐릭터 카드처럼) 총알 아이콘 n개를 우측 상단 모서리에 쌓아서 그린다."""
    bw = size
    bh = int(size * 2.5)
    gap = 3
    total_w = n * (bw + gap) - gap
    ox = x - total_w
    for i in range(n):
        bx = ox + i * (bw + gap)
        # 총알 몸통
        body = pygame.Rect(bx, y + size // 2, bw, bh - size // 2)
        pygame.draw.rect(surf, BULLET_Y, body, border_radius=3)
        pygame.draw.rect(surf, BULLET_DRK, body, 1, border_radius=3)
        # 총알 끝부분 (삼각형 / 둥근 상단)
        pts = [(bx, y + size // 2),
               (bx + bw, y + size // 2),
               (bx + bw // 2, y)]
        pygame.draw.polygon(surf, BULLET_Y, pts)
        pygame.draw.polygon(surf, BULLET_DRK, pts, 1)
        # 테두리 선
        pygame.draw.line(surf, BULLET_DRK, (bx, y + size // 2 + 2),
                         (bx + bw, y + size // 2 + 2))


# ── 프레임 그리기 함수들 ─────────────────────────────────────────────────────────

def draw_parchment_frame(surf: pygame.Surface, rect: pygame.Rect, inner_pad=4):
    """오래된 양피지 프레임을 그린다 (갈색 플레이 카드 + 역할 카드)."""
    r = 10
    _shadow(surf, rect, r)
    # 외곽 테두리 (황갈색)
    outer = rect.inflate(4, 4)
    pygame.draw.rect(surf, BORDER_TAN, outer, border_radius=r + 2)
    pygame.draw.rect(surf, BORDER_DRK, outer, 1, border_radius=r + 2)
    # 양피지 채움
    pygame.draw.rect(surf, PARCHMENT, rect, border_radius=r)
    _parchment_edges(surf, rect, r)
    # 내부 테두리 선
    inner = rect.inflate(-inner_pad * 2, -inner_pad * 2)
    pygame.draw.rect(surf, BORDER_TAN, inner, 1, border_radius=max(4, r - inner_pad))


def draw_blue_frame(surf: pygame.Surface, rect: pygame.Rect):
    """블루 장비 카드 프레임을 그린다."""
    r = 10
    _shadow(surf, rect, r)
    # 외곽 테두리
    outer = rect.inflate(4, 4)
    pygame.draw.rect(surf, BLUE_DRK, outer, border_radius=r + 2)
    # 블루 채움
    pygame.draw.rect(surf, BLUE_BG, rect, border_radius=r)
    # 블루 테두리 내부 선
    pygame.draw.rect(surf, BLUE_BORDER, rect, 4, border_radius=r)


def draw_character_frame(surf: pygame.Surface, rect: pygame.Rect):
    """캐릭터 카드 프레임을 그린다 (녹색 점선 테두리, 크림색 배경)."""
    r = 12
    _shadow(surf, rect, r)
    # 녹색 외곽 테두리
    pygame.draw.rect(surf, CHAR_GREEN_DRK, rect.inflate(6, 6), border_radius=r + 3)
    pygame.draw.rect(surf, CHAR_GREEN, rect.inflate(4, 4), border_radius=r + 2)
    # 크림색 배경
    pygame.draw.rect(surf, CHAR_BG, rect, border_radius=r)
    # 녹색 테두리 안쪽을 따라 그려진 흰색 점들
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


# ── 역할 카드 ─────────────────────────────────────────────────────────────────

def _draw_sheriff_badge(surf, cx, cy, r):
    gold = (215, 182, 58)
    tan  = (188, 148, 60)
    dark = (100,  72, 18)
    # 육각별 (삼각형 두 개)
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
    # 모자 챙
    pygame.draw.ellipse(surf, black, (cx - 28, cy - h // 2 + 12, 56, 14))
    # 모자 윗부분
    pygame.draw.rect(surf, black, (cx - 18, cy - h // 2 - 10, 36, 26), border_radius=4)
    # 머리
    pygame.draw.ellipse(surf, black, (cx - 16, cy - h // 2 + 20, 32, 30))
    # 몸통 (코트)
    pts = [(cx - 22, cy - h // 2 + 48),
           (cx + 22, cy - h // 2 + 48),
           (cx + 28, cy + h // 2),
           (cx - 28, cy + h // 2)]
    pygame.draw.polygon(surf, black, pts)


def _draw_renegade_hat(surf, cx, cy, r):
    black = (30, 20, 10)
    # 모자 챙
    pygame.draw.ellipse(surf, black, (cx - r, cy + r // 4, r * 2, r // 2))
    # 모자 윗부분
    pts = [(cx - int(r * 0.6), cy + r // 4),
           (cx + int(r * 0.6), cy + r // 4),
           (cx + int(r * 0.4), cy - r),
           (cx - int(r * 0.4), cy - r)]
    pygame.draw.polygon(surf, black, pts)
    # 모자 띠
    pygame.draw.line(surf, (80, 60, 20),
                     (cx - int(r * 0.6), cy - int(r * 0.15)),
                     (cx + int(r * 0.6), cy - int(r * 0.15)), 4)
    # 얼굴 윤곽 (단순한 타원)
    pygame.draw.ellipse(surf, (160, 130, 90),
                        (cx - int(r * 0.45), cy + r // 4 - int(r * 0.9),
                         int(r * 0.9), int(r * 1.1)))


def draw_role_card(surf: pygame.Surface, role: Role, rect: pygame.Rect):
    from ui_utils import draw_text
    # ── 이미지 우선 적용 ────────────────────────────────────────────────────
    img = _load(os.path.join("roles", _ROLE_FILE[role]))
    if img:
        _blit_card_image(surf, img, rect)
        _overlay_role_text(surf, role, rect)
        return
    # ── 프로그램으로 그리는 대체 방식 ─────────────────────────────────────────────
    draw_parchment_frame(surf, rect)
    x, y, w, h = rect

    # 제목 배너 영역
    title_h = int(h * 0.22)
    title_bg = pygame.Rect(x + 6, y + 6, w - 12, title_h)
    pygame.draw.rect(surf, PARCHMENT_DRK, title_bg, border_radius=6)
    pygame.draw.rect(surf, BORDER_TAN, title_bg, 1, border_radius=6)
    name_ko = ROLE_NAME_KO[role]
    draw_text(surf, name_ko, "large", TEXT_INK, rect.centerx, y + 16, "center")

    # 일러스트 영역
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
    else:  # RENEGADE(배신자)
        _draw_renegade_hat(surf, icx, icy, icon_r)

    # 목표 텍스트
    obj_y = ill_y + ill_h + 10
    for li, txt in enumerate(_wrap_lines(ROLE_OBJ_KO[role], "small", rect.w - 28)):
        draw_text(surf, txt, "small", TEXT_MID,
                  rect.centerx, obj_y + li * 18, "center")

    # 하단의 역할 색상 강조 바
    bar_h = 18
    bar = pygame.Rect(x + 8, y + h - bar_h - 6, w - 16, bar_h)
    fill = ROLE_FILL[role]
    pygame.draw.rect(surf, fill, bar, border_radius=6)
    draw_text(surf, name_ko, "tiny", (255, 255, 255),
              bar.centerx, bar.centery, "center")


def _overlay_role_text(surf: pygame.Surface, role: Role, rect: pygame.Rect):
    """사진 에셋은 역할 카드 전체를 대체하지만 인쇄된 텍스트가 없으므로,
    실제 카드라면 인쇄되어 있을 역할 이름 + 목표를 반투명한 띠 위에
    덧그려서 어떤 그림 위에서도 글자가 잘 보이도록 한다."""
    from ui_utils import draw_text
    x, y, w, h = rect

    top = pygame.Rect(x, y, w, 32)
    ov = pygame.Surface((top.w, top.h), pygame.SRCALPHA)
    ov.fill((12, 9, 4, 190))
    surf.blit(ov, top.topleft)
    draw_text(surf, ROLE_NAME_KO[role], "large", (255, 250, 235),
              rect.centerx, y + 6, "center")

    lines = _wrap_lines(ROLE_OBJ_KO[role], "small", w - 24)
    band_h = 12 + len(lines) * 18
    band = pygame.Rect(x, y + h - band_h, w, band_h)
    ov2 = pygame.Surface((band.w, band.h), pygame.SRCALPHA)
    ov2.fill((12, 9, 4, 190))
    surf.blit(ov2, band.topleft)
    for li, txt in enumerate(lines):
        draw_text(surf, txt, "small", (225, 218, 200),
                  rect.centerx, band.y + 6 + li * 18, "center")


# ── 캐릭터 카드 ────────────────────────────────────────────────────────────

# 각 캐릭터를 위한 단순 아이콘 (세피아 영역에 그려짐)
def _draw_char_icon(surf, char: CharacterType, cx, cy, r):
    """캐릭터를 대표하는 단순한 아이콘을 그린다."""
    dark   = (80, 55, 20)
    sepia2 = (170, 138, 85)
    gold   = (210, 172, 45)

    if char == CharacterType.BART_CASSIDY:
        # 카드가 날아가는 모습
        for i, off in enumerate((-15, 0, 15)):
            cr = pygame.Rect(cx + off - 8, cy - r // 2 - 10, 18, 26)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=3)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=3)
    elif char == CharacterType.BLACK_JACK:
        # 공개되는 카드
        cr = pygame.Rect(cx - 14, cy - 20, 28, 38)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=3)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=3)
        draw_heart(surf, cx, cy + 2, 10)
    elif char == CharacterType.CALAMITY_JANET:
        # BANG! ↔ Missed! 화살표
        pygame.draw.line(surf, dark, (cx - 22, cy - 8), (cx + 22, cy - 8), 2)
        pygame.draw.polygon(surf, dark, [(cx + 22, cy - 8),
                                         (cx + 14, cy - 14), (cx + 14, cy - 2)])
        pygame.draw.line(surf, dark, (cx + 22, cy + 8), (cx - 22, cy + 8), 2)
        pygame.draw.polygon(surf, dark, [(cx - 22, cy + 8),
                                         (cx - 14, cy + 14), (cx - 14, cy + 2)])
    elif char == CharacterType.EL_GRINGO:
        # 카드를 훔치는 손
        cr = pygame.Rect(cx - 10, cy - 18, 20, 28)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
        # 카드를 향하는 화살표
        pygame.draw.line(surf, dark, (cx - 28, cy), (cx - 14, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx - 14, cy),
                                         (cx - 20, cy - 5), (cx - 20, cy + 5)])
    elif char in (CharacterType.JESSE_JONES, CharacterType.PEDRO_RAMIREZ):
        # 버림 더미/플레이어에서 손패로 향하는 화살표
        pygame.draw.line(surf, dark, (cx - 26, cy), (cx, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx, cy), (cx - 8, cy - 5), (cx - 8, cy + 5)])
        cr = pygame.Rect(cx + 4, cy - 15, 20, 28)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.JOURDONNAIS:
        # 나무통
        pygame.draw.ellipse(surf, sepia2, (cx - 18, cy - r + 6, 36, 16))
        pygame.draw.rect(surf, sepia2, (cx - 18, cy - r + 14, 36, 28))
        pygame.draw.ellipse(surf, sepia2, (cx - 18, cy - r + 36, 36, 14))
        for ly in (cy - r + 20, cy - r + 28):
            pygame.draw.line(surf, dark, (cx - 18, ly), (cx + 18, ly), 1)
        pygame.draw.rect(surf, dark, (cx - 18, cy - r + 14, 36, 28), 1)
    elif char == CharacterType.KIT_CARLSON:
        # 검토 중인 카드 3장 → 2장 선택
        for i, off in enumerate((-22, 0, 22)):
            cr = pygame.Rect(cx + off - 9, cy - 20, 18, 26)
            col = gold if i < 2 else PARCHMENT_DRK
            pygame.draw.rect(surf, col, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.LUCKY_DUKE:
        # 뒤집힌 카드 두 장
        for off in (-12, 8):
            cr = pygame.Rect(cx + off, cy - 20, 18, 26)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.PAUL_REGRET:
        # 거리 +1 (말/인물이 멀어지는 모습)
        pygame.draw.circle(surf, sepia2, (cx - 16, cy), 12)
        pygame.draw.circle(surf, dark, (cx - 16, cy), 12, 1)
        draw_text_tiny(surf, "+1", dark, cx + 8, cy - 7)
    elif char == CharacterType.ROSE_DOOLAN:
        # 조준경/망원경
        pygame.draw.rect(surf, sepia2, (cx - 22, cy - 6, 44, 10), border_radius=4)
        pygame.draw.circle(surf, dark, (cx + 22, cy), 9, 2)
        pygame.draw.rect(surf, dark, (cx - 22, cy - 6, 44, 10), 1, border_radius=4)
    elif char == CharacterType.SID_KETCHUM:
        # 카드 2장 → HP 하트
        for i, off in enumerate((-14, 0)):
            cr = pygame.Rect(cx + off, cy - 20, 16, 22)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
        pygame.draw.line(surf, dark, (cx + 18, cy), (cx + 26, cy), 2)
        draw_heart(surf, cx + 35, cy, 9)
    elif char == CharacterType.SLAB_KILLER:
        # Missed! 카드 2장 필요
        for i, off in enumerate((-14, 4)):
            cr = pygame.Rect(cx + off, cy - 15, 16, 22)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
            draw_text_tiny(surf, "M", dark, cx + off + 8, cy - 8)
    elif char == CharacterType.SUZY_LAFAYETTE:
        # 빈 손패 → 카드 드로우
        draw_text_tiny(surf, "0장", dark, cx - 18, cy - 10)
        pygame.draw.line(surf, dark, (cx - 5, cy), (cx + 5, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx + 5, cy), (cx - 1, cy - 5), (cx - 1, cy + 5)])
        cr = pygame.Rect(cx + 8, cy - 14, 16, 22)
        pygame.draw.rect(surf, gold, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.VULTURE_SAM:
        # 탈락한 플레이어의 모든 카드
        for i in range(3):
            cr = pygame.Rect(cx - 16 + i * 10, cy - 16 + i * 4, 18, 24)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
    elif char == CharacterType.WILLY_KID:
        # BANG! × N (무제한)
        draw_text_tiny(surf, "BANG!", dark, cx - 10, cy - 10)
        draw_text_tiny(surf, "× N", dark, cx + 2, cy + 2)
    else:
        # 기본 총 아이콘
        pygame.draw.rect(surf, dark, (cx - 22, cy - 6, 30, 10), border_radius=3)
        pygame.draw.rect(surf, dark, (cx + 6, cy - 16, 12, 10), border_radius=2)
        pygame.draw.line(surf, dark, (cx - 22, cy + 4), (cx - 14, cy + 14), 2)


def draw_heart(surf, cx, cy, r, color=(200, 50, 45), filled=True):
    """작은 하트 모양을 그린다 (filled=False면 윤곽선만 그림)."""
    pts = []
    for deg in range(0, 360, 8):
        t = math.radians(deg)
        hx = r * (16 * math.sin(t) ** 3) / 16
        hy = -r * (13 * math.cos(t) - 5 * math.cos(2 * t) -
                   2 * math.cos(3 * t) - math.cos(4 * t)) / 16
        pts.append((cx + hx, cy + hy))
    if len(pts) >= 3:
        if filled:
            pygame.draw.polygon(surf, color, pts)
        else:
            pygame.draw.polygon(surf, color, pts, 2)


def draw_text_tiny(surf, text, color, x, y):
    """ui_utils를 재귀적으로 import하지 않는 최소한의 텍스트 그리기."""
    from ui_utils import draw_text
    draw_text(surf, text, "tiny", color, x, y)


def draw_character_card(surf: pygame.Surface,
                        char: CharacterType,
                        max_hp: int,
                        rect: pygame.Rect):
    from ui_utils import draw_text
    info = CHARACTERS[char]
    # ── 이미지 우선 적용 ────────────────────────────────────────────────────
    img = _load(os.path.join("characters", _CHAR_FILE[char]))
    if img:
        _blit_card_image(surf, img, rect)
        _overlay_char_text(surf, info, max_hp, rect)
        return
    # ── 프로그램으로 그리는 대체 방식 ─────────────────────────────────────────────
    draw_character_frame(surf, rect)
    x, y, w, h = rect

    # 제목
    title_y = y + 10
    draw_text(surf, info.name_en.upper(), "sub", TEXT_INK,
              rect.centerx - 20, title_y, "center")

    # HP 총알 (우측 상단)
    draw_bullets(surf, max_hp, x + w - 8, title_y + 2, size=8)

    # 세피아 일러스트 영역
    art_y = title_y + 26
    art_h = int(h * 0.42)
    art   = pygame.Rect(x + 10, art_y, w - 20, art_h)
    pygame.draw.rect(surf, CHAR_SEPIA, art, border_radius=6)
    pygame.draw.rect(surf, PARCHMENT_DRK, art, 1, border_radius=6)

    # 아트 영역에 캐릭터 아이콘 표시
    _draw_char_icon(surf, char, art.centerx, art.centery,
                    min(art.w, art.h) // 2 - 6)

    # 한글 이름 바
    bar_y = art_y + art_h + 6
    draw_text(surf, info.name_ko, "small", TEXT_INK,
              rect.centerx, bar_y, "center")

    # 설명
    desc_y = bar_y + 20
    for li, txt in enumerate(_wrap_lines(info.desc, "tiny", w - 20)):
        draw_text(surf, txt, "tiny", TEXT_MID,
                  rect.centerx, desc_y + li * 16, "center")


def _overlay_char_text(surf: pygame.Surface, info, max_hp: int, rect: pygame.Rect):
    """사진 에셋은 캐릭터 카드 전체를 대체하지만 인쇄된 텍스트가 없으므로,
    실제 카드라면 인쇄되어 있을 이름/설명/HP를 반투명한 띠 위에 덧그려서
    어떤 그림 위에서도 글자가 잘 보이도록 한다."""
    from ui_utils import draw_text
    x, y, w, h = rect

    lines = _wrap_lines(info.desc, "tiny", w - 24)
    band_h = 24 + len(lines) * 16
    band = pygame.Rect(x, y + h - band_h, w, band_h)
    ov = pygame.Surface((band.w, band.h), pygame.SRCALPHA)
    ov.fill((12, 9, 4, 200))
    surf.blit(ov, band.topleft)
    draw_text(surf, info.name_ko, "small", (255, 250, 235),
              rect.centerx, band.y + 6, "center")
    for li, txt in enumerate(lines):
        draw_text(surf, txt, "tiny", (225, 218, 200),
                  rect.centerx, band.y + 24 + li * 16, "center")

    # HP 총알, 우측 상단 모서리, 대비를 위해 작은 어두운 배경 위에 표시
    bw, bh, gap = 8, 20, 3
    bullets_w = max_hp * (bw + gap) - gap
    pad = pygame.Rect(x + w - 14 - bullets_w, y + 4, bullets_w + 12, bh + 12)
    ov2 = pygame.Surface((pad.w, pad.h), pygame.SRCALPHA)
    ov2.fill((12, 9, 4, 170))
    surf.blit(ov2, pad.topleft)
    draw_bullets(surf, max_hp, x + w - 8, y + 10, size=8)


# ── 게임 카드 (작은 크기, 손패용) ────────────────────────────────────────────────

# 카드의 아트 영역에 그려지는, 카드 종류별 단순 아이콘
def _draw_card_icon(surf, card: Card, cx, cy, r):
    dark  = TEXT_INK
    red   = (190, 45, 38)
    gold  = (210, 172, 45)
    blue  = (60, 105, 185)
    green = (55, 128, 60)

    ct = card.card_type

    if ct == CardType.BANG:
        # 폭발 스타버스트
        for i in range(8):
            a = math.radians(i * 45)
            ex = cx + int(r * 0.85 * math.cos(a))
            ey = cy + int(r * 0.85 * math.sin(a))
            pygame.draw.line(surf, (210, 120, 30), (cx, cy), (ex, ey), 2)
        pygame.draw.circle(surf, (215, 80, 28), (cx, cy), r // 2)
        pygame.draw.circle(surf, dark, (cx, cy), r // 2, 1)

    elif ct == CardType.MISSED:
        # 날아가는 모자
        pygame.draw.ellipse(surf, (160, 130, 80), (cx - r, cy, r * 2, r // 2))
        pygame.draw.rect(surf, (120, 95, 55), (cx - int(r * 0.6), cy - r, int(r * 1.2), r + 2), border_radius=3)

    elif ct == CardType.BEER:
        # 맥주잔
        pygame.draw.rect(surf, (210, 185, 65), (cx - r // 2, cy - int(r * 0.8), r, int(r * 1.6)), border_radius=3)
        pygame.draw.rect(surf, dark, (cx - r // 2, cy - int(r * 0.8), r, int(r * 1.6)), 1, border_radius=3)
        # 손잡이
        pygame.draw.arc(surf, dark, (cx + r // 2 - 2, cy - r // 4, r // 2, r // 2), 0, math.pi, 2)

    elif ct == CardType.STAGECOACH:
        # 카드 아이콘 두 개
        for off in (-10, 6):
            cr = pygame.Rect(cx + off, cy - 14, 14, 20)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)

    elif ct == CardType.WELLS_FARGO:
        # 카드 아이콘 세 개
        for off in (-16, -4, 8):
            cr = pygame.Rect(cx + off, cy - 14, 14, 20)
            pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
            pygame.draw.rect(surf, dark, cr, 1, border_radius=2)

    elif ct == CardType.CAT_BALOU:
        # X자가 그려진 카드
        cr = pygame.Rect(cx - 12, cy - 16, 24, 32)
        pygame.draw.rect(surf, PARCHMENT_LGT, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)
        pygame.draw.line(surf, red, cr.topleft, cr.bottomright, 2)
        pygame.draw.line(surf, red, cr.topright, cr.bottomleft, 2)

    elif ct == CardType.PANIC:
        # 훔치는 화살표
        pygame.draw.line(surf, dark, (cx - r, cy), (cx + r, cy), 2)
        pygame.draw.polygon(surf, dark, [(cx + r, cy), (cx + r - 7, cy - 5), (cx + r - 7, cy + 5)])
        cr = pygame.Rect(cx + r - 2, cy - 14, 16, 22)
        pygame.draw.rect(surf, gold, cr, border_radius=2)
        pygame.draw.rect(surf, dark, cr, 1, border_radius=2)

    elif ct == CardType.INDIANS:
        # 화살표
        pygame.draw.line(surf, (140, 80, 30), (cx - r, cy), (cx + r, cy), 3)
        pygame.draw.polygon(surf, (140, 80, 30), [(cx + r, cy), (cx + r - 8, cy - 6), (cx + r - 8, cy + 6)])
        # 깃털
        for fy in (-6, 0, 6):
            pygame.draw.line(surf, (160, 100, 40), (cx - r + 4, cy + fy), (cx - r + 12, cy + fy - 4), 1)

    elif ct == CardType.GATLING:
        # X (모든 플레이어) + 총
        pygame.draw.line(surf, red, (cx - r, cy - r // 2), (cx + r, cy + r // 2), 2)
        pygame.draw.line(surf, red, (cx + r, cy - r // 2), (cx - r, cy + r // 2), 2)

    elif ct == CardType.SALOON:
        # 여러 개의 + 기호 (전체 회복)
        for dx, dy in ((-10, -5), (5, -5), (-5, 8)):
            pygame.draw.line(surf, green, (cx + dx - 5, cy + dy), (cx + dx + 5, cy + dy), 2)
            pygame.draw.line(surf, green, (cx + dx, cy + dy - 5), (cx + dx, cy + dy + 5), 2)

    elif ct == CardType.GEN_STORE:
        # 상점 정면 모양
        pygame.draw.rect(surf, (180, 145, 85), (cx - r, cy - r // 3, r * 2, int(r * 1.3)), border_radius=2)
        pygame.draw.rect(surf, dark, (cx - r, cy - r // 3, r * 2, int(r * 1.3)), 1, border_radius=2)
        # 차양
        pts = [(cx - r - 3, cy - r // 3), (cx + r + 3, cy - r // 3),
               (cx + r - 4, cy - r), (cx - r + 4, cy - r)]
        pygame.draw.polygon(surf, (160, 50, 40), pts)

    elif ct == CardType.DUEL:
        # 서로 마주보는 권총 두 자루
        _draw_mini_gun(surf, cx - 8, cy, dark, flip=False)
        _draw_mini_gun(surf, cx + 8, cy, dark, flip=True)

    elif ct in (CardType.VOLCANIC, CardType.SCHOFIELD,
                CardType.REMINGTON, CardType.CARABINE, CardType.WINCHESTER):
        # 총 실루엣 + 사거리 원
        _draw_mini_gun(surf, cx - 4, cy - 2, dark)
        # 사거리 표시 원
        rn = GUN_RANGE_NUM.get(ct, 1)
        cr2 = pygame.Rect(cx - 10, cy + 6, 20, 20)
        pygame.draw.circle(surf, blue, cr2.center, 10)
        pygame.draw.circle(surf, dark, cr2.center, 10, 1)
        # 십자선
        pygame.draw.line(surf, dark, (cr2.centerx - 7, cr2.centery),
                         (cr2.centerx + 7, cr2.centery), 1)
        pygame.draw.line(surf, dark, (cr2.centerx, cr2.centery - 7),
                         (cr2.centerx, cr2.centery + 7), 1)
        draw_text_tiny(surf, str(rn), (255, 255, 255), cr2.centerx, cr2.centery - 5)

    elif ct == CardType.BARREL:
        # 하트가 있는 나무통 = 회피
        pygame.draw.ellipse(surf, (165, 115, 55), (cx - 14, cy - r + 4, 28, 12))
        pygame.draw.rect(surf, (145, 95, 40), (cx - 14, cy - r + 10, 28, r - 4), border_radius=2)
        pygame.draw.ellipse(surf, (155, 105, 45), (cx - 14, cy + 2, 28, 10))
        pygame.draw.rect(surf, dark, (cx - 14, cy - r + 10, 28, r - 4), 1, border_radius=2)
        draw_heart(surf, cx + 10, cy, 7)

    elif ct == CardType.SCOPE:
        # 망원경
        pygame.draw.rect(surf, (140, 110, 55), (cx - r, cy - 5, r * 2, 10), border_radius=4)
        pygame.draw.circle(surf, dark, (cx + r, cy), 8, 1)

    elif ct == CardType.MUSTANG:
        # 말 실루엣 (매우 단순하게)
        pygame.draw.ellipse(surf, dark, (cx - r, cy - 6, r * 2 - 6, 14))
        pygame.draw.ellipse(surf, dark, (cx - r // 2, cy - r, 14, 16))

    elif ct == CardType.JAIL:
        # 창살
        for bx in range(cx - 10, cx + 14, 8):
            pygame.draw.line(surf, dark, (bx, cy - r + 4), (bx, cy + r - 4), 2)
        pygame.draw.line(surf, dark, (cx - 12, cy - r + 4), (cx + 14, cy - r + 4), 2)
        pygame.draw.line(surf, dark, (cx - 12, cy + r - 4), (cx + 14, cy + r - 4), 2)
        draw_heart(surf, cx + 18, cy, 7)

    elif ct == CardType.DYNAMITE:
        # 다이너마이트 막대
        pygame.draw.rect(surf, red, (cx - 8, cy - r + 6, 16, r * 2 - 10), border_radius=3)
        pygame.draw.rect(surf, dark, (cx - 8, cy - r + 6, 16, r * 2 - 10), 1, border_radius=3)
        # 도화선
        pygame.draw.line(surf, (210, 165, 45), (cx, cy - r + 6), (cx + 6, cy - r - 4), 2)


GUN_RANGE_NUM = {
    CardType.VOLCANIC:  1,
    CardType.SCHOFIELD: 2,
    CardType.REMINGTON: 3,
    CardType.CARABINE:  4,
    CardType.WINCHESTER: 5,
}


def _draw_mini_gun(surf, cx, cy, color, flip=False):
    """매우 작은 총 모양을 그린다."""
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
    """(x, y) 위치에 크기 (w, h)로 스타일이 적용된 게임 카드를 그린다."""
    from ui_utils import draw_text
    from cards import Suit
    rect = pygame.Rect(x, y, w, h)

    if face_down:
        _shadow(surf, rect, 8)
        pygame.draw.rect(surf, PARCHMENT_DRK, rect, border_radius=8)
        pygame.draw.rect(surf, BORDER_TAN, rect, 3, border_radius=8)
        # 뒷면 패턴
        inner = rect.inflate(-10, -10)
        pygame.draw.rect(surf, PARCHMENT, inner, border_radius=6)
        pygame.draw.rect(surf, BORDER_TAN, inner, 1, border_radius=6)
        return

    # ── 이미지 우선 적용 ────────────────────────────────────────────────────
    img = _load(os.path.join("game", _GAME_CARD_FILE[card.card_type]))
    if img:
        _blit_card_image(surf, img, rect)
        # 이미지 위에 선택 강조 표시를 그림
        if selected:
            pygame.draw.rect(surf, (255, 215, 0), rect, 3, border_radius=10)
        elif playable:
            pygame.draw.rect(surf, (80, 175, 75), rect, 2, border_radius=10)
        elif discard_mode:
            pygame.draw.rect(surf, (190, 50, 40), rect, 2, border_radius=10)
        return
    # ── 프로그램으로 그리는 대체 방식 ─────────────────────────────────────────────

    if card.is_blue:
        draw_blue_frame(surf, rect)
        text_color = TEXT_BLUE_INK
        bg_col = BLUE_BG
    else:
        draw_parchment_frame(surf, rect)
        text_color = TEXT_INK
        bg_col = PARCHMENT

    # 선택/플레이 가능 강조 표시
    if selected:
        pygame.draw.rect(surf, (255, 215, 0), rect, 3, border_radius=10)
    elif playable:
        pygame.draw.rect(surf, (80, 175, 75), rect, 2, border_radius=10)
    elif discard_mode:
        pygame.draw.rect(surf, (190, 50, 40), rect, 2, border_radius=10)

    # 무늬+숫자 (좌측 상단)
    from cards import Suit
    from ui_utils import draw_suit_icon
    sv_color = (180, 40, 35) if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else TEXT_INK
    val_str = {1: "A", 11: "J", 12: "Q", 13: "K"}.get(card.value, str(card.value))
    draw_suit_icon(surf, card.suit.value, x + 8, y + 6, 10, sv_color)
    draw_text(surf, val_str, "tiny", sv_color, x + 4, y + 14)

    # 제목 (상단 부분) — 글자 수로 추측하지 않고 실제 렌더링 너비를 측정하여,
    # "Missed!"처럼 짧지만 글자 수가 많이 잡히는 이름이 단어 중간에서
    # 잘리지 않고 한 줄에 유지되도록 한다.
    name = card.name
    title_y = y + h // 5
    from ui_utils import font as get_font
    if get_font("small").size(name)[0] <= w - 8:
        draw_text(surf, name, "small", text_color, x + w // 2, title_y, "center")
    else:
        # 두 줄로 표시: 중간 근처에 공백이 있으면 그 자리에서 줄을 나누고,
        # 없으면 글자 수 기준으로 나눈다.
        mid = name.find(" ", len(name) // 2)
        if mid == -1:
            mid = name.rfind(" ", 0, len(name) // 2)
        if mid == -1:
            mid = len(name) // 2
        draw_text(surf, name[:mid], "tiny", text_color, x + w // 2, title_y - 6, "center")
        draw_text(surf, name[mid:].strip(), "tiny", text_color, x + w // 2, title_y + 7, "center")

    # 카드 아이콘 / 아트 영역 (중앙)
    art_cx = x + w // 2
    art_cy = y + int(h * 0.58)
    icon_r = min(w, h) // 4
    _draw_card_icon(surf, card, art_cx, art_cy, icon_r)

    # 블루 장비: 하단 중앙에 사거리 원 (아이콘에서 이미 그려짐)
    # 양피지: 하단에 종류 배지
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
