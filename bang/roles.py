from enum import Enum
import random


class Role(Enum):
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
    # Sheriff always at index 0
    si = pool.index(Role.SHERIFF)
    pool[0], pool[si] = pool[si], pool[0]
    return pool


ROLE_DESC = {
    Role.SHERIFF:  "보안관 – 무법자와 배신자를 처치하세요. HP +1",
    Role.DEPUTY:   "부관 – 보안관을 지켜주세요.",
    Role.OUTLAW:   "무법자 – 보안관을 처치하세요!",
    Role.RENEGADE: "배신자 – 마지막 생존자가 되어 보안관과 결투",
}
