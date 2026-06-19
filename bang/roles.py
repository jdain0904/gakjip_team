from enum import Enum
import random


class Role(Enum):
    """플레이어의 승리 조건을 결정하는 진영. 보안관만 공개 상태로 시작하고
    나머지는 비공개로 시작한다."""
    SHERIFF  = "보안관"
    DEPUTY   = "부관"
    OUTLAW   = "무법자"
    RENEGADE = "배신자"


_ROLE_SETS = {
    4: [Role.SHERIFF, Role.RENEGADE, Role.OUTLAW, Role.OUTLAW],
    5: [Role.SHERIFF, Role.RENEGADE, Role.OUTLAW, Role.OUTLAW, Role.DEPUTY],
    6: [Role.SHERIFF, Role.RENEGADE, Role.OUTLAW, Role.OUTLAW, Role.OUTLAW, Role.DEPUTY],
    7: [Role.SHERIFF, Role.RENEGADE, Role.OUTLAW, Role.OUTLAW, Role.OUTLAW, Role.DEPUTY, Role.DEPUTY],
}


def assign_roles(n: int) -> list[Role]:
    pool = _ROLE_SETS[n][:]
    random.shuffle(pool)
    return pool


ROLE_DESC = {
    Role.SHERIFF:  "보안관 – 무법자와 배신자를 처치하세요. HP +1",
    Role.DEPUTY:   "부관 – 보안관을 지켜주세요.",
    Role.OUTLAW:   "무법자 – 보안관을 처치하세요!",
    Role.RENEGADE: "배신자 – 마지막 생존자가 되어 보안관과 결투",
}
