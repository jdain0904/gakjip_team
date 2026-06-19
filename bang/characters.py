from enum import Enum
from dataclasses import dataclass
import random


class CharacterType(Enum):
    """기본판 16개 캐릭터 중 하나. 각 캐릭터는 고유한 패시브 또는 액티브
    능력을 가진다 (자세한 설명은 아래 CHARACTERS 참고)."""
    BART_CASSIDY   = "bart_cassidy"
    BLACK_JACK     = "black_jack"
    CALAMITY_JANET = "calamity_janet"
    EL_GRINGO      = "el_gringo"
    JESSE_JONES    = "jesse_jones"
    JOURDONNAIS    = "jourdonnais"
    KIT_CARLSON    = "kit_carlson"
    LUCKY_DUKE     = "lucky_duke"
    PAUL_REGRET    = "paul_regret"
    PEDRO_RAMIREZ  = "pedro_ramirez"
    ROSE_DOOLAN    = "rose_doolan"
    SID_KETCHUM    = "sid_ketchum"
    SLAB_KILLER    = "slab_killer"
    SUZY_LAFAYETTE = "suzy_lafayette"
    VULTURE_SAM    = "vulture_sam"
    WILLY_KID      = "willy_kid"


@dataclass(frozen=True)
class CharacterInfo:
    """CharacterType 하나에 대한 고정 정보: 영문/한글 이름, 시작 체력,
    캐릭터 카드에 표시되는 한글 능력 설명을 담는다."""
    name_en: str
    name_ko: str
    base_hp: int   # without Sheriff +1 bonus
    desc: str


CHARACTERS: dict[CharacterType, CharacterInfo] = {
    CharacterType.BART_CASSIDY: CharacterInfo(
        "Bart Cassidy", "바트 카시디", 4,
        "HP를 잃을 때마다 카드 1장 드로우"
    ),
    CharacterType.BLACK_JACK: CharacterInfo(
        "Black Jack", "블랙 잭", 4,
        "드로우 2번째 카드 공개: 빨간 무늬면 카드 1장 추가"
    ),
    CharacterType.CALAMITY_JANET: CharacterInfo(
        "Calamity Janet", "캘러미티 재닛", 4,
        "BANG!↔Missed! 서로 대체 사용 가능"
    ),
    CharacterType.EL_GRINGO: CharacterInfo(
        "El Gringo", "엘 그링고", 3,
        "HP 잃을 때마다 공격자에게서 카드 1장 훔침"
    ),
    CharacterType.JESSE_JONES: CharacterInfo(
        "Jesse Jones", "제시 존스", 4,
        "드로우 1번째 카드를 다른 플레이어 손에서 가져올 수 있음"
    ),
    CharacterType.JOURDONNAIS: CharacterInfo(
        "Jourdonnais", "주르도네", 4,
        "항상 나무통 장착 (BANG! 받을 때 ♥면 Missed!)"
    ),
    CharacterType.KIT_CARLSON: CharacterInfo(
        "Kit Carlson", "킷 칼슨", 4,
        "드로우 시 상위 3장 공개, 2장 선택 후 1장 덱 위 반환"
    ),
    CharacterType.LUCKY_DUKE: CharacterInfo(
        "Lucky Duke", "럭키 듀크", 4,
        "드로우! 판정 시 카드 2장 뒤집어 유리한 것 선택"
    ),
    CharacterType.PAUL_REGRET: CharacterInfo(
        "Paul Regret", "폴 리그렛", 3,
        "항상 무스탕 장착 (타인에게 내 거리 +1)"
    ),
    CharacterType.PEDRO_RAMIREZ: CharacterInfo(
        "Pedro Ramirez", "페드로 라미레즈", 4,
        "드로우 1번째 카드를 버림 더미에서 가져올 수 있음"
    ),
    CharacterType.ROSE_DOOLAN: CharacterInfo(
        "Rose Doolan", "로즈 둘란", 4,
        "항상 조준경 장착 (타인 거리 -1로 인식)"
    ),
    CharacterType.SID_KETCHUM: CharacterInfo(
        "Sid Ketchum", "시드 케첨", 4,
        "언제든지 카드 2장 버려서 HP 1 회복"
    ),
    CharacterType.SLAB_KILLER: CharacterInfo(
        "Slab the Killer", "슬랩 더 킬러", 4,
        "자신의 BANG!을 막으려면 Missed! 2장 필요"
    ),
    CharacterType.SUZY_LAFAYETTE: CharacterInfo(
        "Suzy Lafayette", "수지 라파예트", 4,
        "손패가 비면 즉시 카드 1장 드로우"
    ),
    CharacterType.VULTURE_SAM: CharacterInfo(
        "Vulture Sam", "벌처 샘", 4,
        "플레이어 탈락 시 그 플레이어 모든 카드를 가져감"
    ),
    CharacterType.WILLY_KID: CharacterInfo(
        "Willy the Kid", "윌리 더 키드", 4,
        "BANG!을 턴당 무제한으로 사용 가능"
    ),
}


def assign_characters(n: int) -> list[CharacterType]:
    pool = list(CharacterType)
    random.shuffle(pool)
    return pool[:n]
