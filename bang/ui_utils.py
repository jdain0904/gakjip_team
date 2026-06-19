"""모든 화면에서 공유하는 UI 헬퍼 함수들."""
import math
import os
import pygame
from constants import WHITE, GRAY, DIM


_fonts: dict[str, pygame.font.Font] = {}

# 내장된 한글 폰트 (네이버 나눔고딕, SIL OFL 1.1 — 함께 들어있는 LICENSE
# 파일 참고). 이 폰트를 직접 로드하면 게임이 배포되는 모든 머신에서 어떤
# 시스템 폰트가 설치되어 있는지(설치되어 있기는 한지)와 무관하게 한글이
# 올바르게 렌더링되는 것이 보장된다 — 이전 방식은 설치된 폰트 이름을
# 추측하는 데 의존했기 때문에, 해당 특정 폰트들이 없는 시스템에서는
# 빈 칸/깨진 글자(tofu)가 조용히 나타나는 문제가 있었다.
_BUNDLED_FONT = os.path.join(os.path.dirname(__file__), "assets", "fonts", "NanumGothic.ttf")


def _find_fallback_font_path() -> str | None:
    """내장 폰트 파일이 어떤 이유로 없을 때만 사용된다.

    pygame.font.SysFont()는 절대 실패하지 않는다 — 알 수 없는 이름이
    들어오면 라틴 문자 전용 기본 폰트로 조용히 대체해버린다 — 그래서
    이 함수는 각 후보를 match_font()(실제 파일 경로 또는 None을 반환)로
    직접 확인한 뒤 그 정확한 파일을 바로 로드하며, SysFont가 다른 매칭
    경로를 통해 이름을 다시 알아서 해석하도록 맡기지 않는다.
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
    """카드 무늬 기호를 도형으로 그린다 (폰트 불필요)."""
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
    """위에서 아래로 부드럽게 변하는 색상 그라디언트로 채워진 Surface를 만든다."""
    surf = pygame.Surface((max(1, w), max(1, h)))
    h = max(1, h)
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(surf, col, (0, y), (w, y))
    return surf


def radial_vignette(w: int, h: int, max_alpha: int = 130, steps: int = 28) -> pygame.Surface:
    """가장자리로 갈수록 부드럽게 어두워지는 투명 Surface를 만든다."""
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
    """라벨이 있는 클릭 가능한 둥근 사각형 — 모든 화면의 마우스 상호작용
    (메뉴 선택, 플레이/턴 종료, 대상 선택 등)이 이 클래스로 만들어진다;
    draw()는 그리기를, clicked()는 좌클릭 히트 판정을 담당한다."""
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
