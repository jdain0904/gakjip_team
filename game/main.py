import asyncio
import pygame
import sys
import random
import math
from abc import ABC, abstractmethod

pygame.init()
WIDTH, HEIGHT = 900, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Space Guardian: Mecha Boss")
clock = pygame.time.Clock()

WHITE = (245, 245, 245)
BLACK = (30, 30, 30)
GRAY = (100, 100, 110)
DARK_GRAY = (50, 50, 60)
GREEN = (80, 200, 120)
RED = (230, 80, 80)
ORANGE = (255, 140, 0)
YELLOW = (255, 220, 70)
PURPLE = (180, 80, 255)
CYAN = (80, 220, 255)

font = pygame.font.SysFont("Arial", 24)
big_font = pygame.font.SysFont("Arial", 60)

PLAYER_BULLET_SPEED = -10.5
shake_timer = 0
shake_intensity = 0


def apply_shake():
    if shake_timer > 0:
        return (random.randint(-shake_intensity, shake_intensity),
                random.randint(-shake_intensity, shake_intensity))
    return (0, 0)


class Explosion:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.timer = 20

    def update(self): self.timer -= 1

    def draw(self, s, offset):
        if self.timer > 0:
            pygame.draw.circle(s, ORANGE,
                               (int(self.x + offset[0]), int(self.y + offset[1])),
                               30 - self.timer, 2)


class PhaseEffect:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.timer = 40

    def update(self): self.timer -= 1

    def draw(self, s, offset):
        r = (40 - self.timer) * 5
        pygame.draw.circle(s, RED,
                           (int(self.x + offset[0]), int(self.y + offset[1])), r, 2)


class Shockwave:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.radius, self.max_radius = 10, 180
        self.alive = True

    def update(self):
        self.radius += 10
        if self.radius > self.max_radius: self.alive = False

    def draw(self, s, offset):
        pygame.draw.circle(s, CYAN,
                           (int(self.x + offset[0]), int(self.y + offset[1])),
                           int(self.radius), 3)


class GameObject(ABC):
    def __init__(self, x, y, color):
        self.x, self.y, self.color = x, y, color
        self.alive = True

    @abstractmethod
    def update(self): pass

    @abstractmethod
    def draw(self, s, offset): pass


class Player(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, GREEN)
        self.radius = 20
        self.speed = 7
        self.hp = 3
        self.max_hp = 3
        self.invincible = 0
        self.laser_gauge = 100
        self.damage = 1
        self.ammo = 100
        self.max_ammo = 100
        self.reloading = False
        self.reload_timer = 0

    def update(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]: self.x -= self.speed
        if keys[pygame.K_RIGHT]: self.x += self.speed
        if keys[pygame.K_UP]: self.y -= self.speed
        if keys[pygame.K_DOWN]: self.y += self.speed
        self.x = max(self.radius, min(WIDTH - self.radius, self.x))
        self.y = max(self.radius, min(HEIGHT - self.radius, self.y))
        if self.invincible > 0: self.invincible -= 1
        if self.laser_gauge < 100: self.laser_gauge += 0.25
        if self.reloading:
            self.reload_timer -= 1
            if self.reload_timer <= 0:
                self.ammo = self.max_ammo
                self.reloading = False

    def draw(self, s, offset):
        color = self.color if self.invincible % 10 < 5 else WHITE
        pygame.draw.polygon(s, color, [
            (self.x + offset[0], self.y - 25 + offset[1]),
            (self.x - 20 + offset[0], self.y + 15 + offset[1]),
            (self.x + 20 + offset[0], self.y + 15 + offset[1])
        ])
        if random.random() > 0.5:
            pygame.draw.circle(s, CYAN,
                               (int(self.x + offset[0]), int(self.y + 20 + offset[1])), 8)

    def get_rect(self):
        return pygame.Rect(self.x - 18, self.y - 20, 36, 40)

    def shoot(self):
        return [Bullet(self.x - 12, self.y, PLAYER_BULLET_SPEED, self.damage),
                Bullet(self.x + 12, self.y, PLAYER_BULLET_SPEED, self.damage)]


class Bullet(GameObject):
    def __init__(self, x, y, dy, damage, color=YELLOW):
        super().__init__(x, y, color)
        self.dy, self.damage = dy, damage

    def update(self):
        self.y += self.dy
        if self.y < -50 or self.y > HEIGHT + 50: self.alive = False

    def draw(self, s, offset):
        pygame.draw.rect(s, self.color,
                         (int(self.x - 3 + offset[0]), int(self.y - 8 + offset[1]), 6, 16))

    def get_rect(self): return pygame.Rect(self.x - 3, self.y - 8, 6, 16)


class EnemyBullet(Bullet):
    def __init__(self, x, y, dx, dy):
        super().__init__(x, y, dy, 1, RED)
        self.dx = dx

    def update(self):
        self.x += self.dx
        self.y += self.dy
        if self.y > HEIGHT + 50 or self.y < -50 or self.x < -50 or self.x > WIDTH + 50:
            self.alive = False


class PlayerLaser:
    def __init__(self, x):
        self.x, self.timer = x, 15

    def update(self): self.timer -= 1

    def draw(self, s, offset):
        w = int(2 + (15 - self.timer) * 1.2)
        pygame.draw.line(s, CYAN, (self.x + offset[0], 0), (self.x + offset[0], HEIGHT), w)

    def rect(self): return pygame.Rect(self.x - 10, 0, 20, HEIGHT)


class FormationEnemy(GameObject):
    def __init__(self, x, y, tx, ty):
        super().__init__(x, y, RED)
        self.size, self.tx, self.ty, self.state = 26, tx, ty, "enter"
        self.shoot_timer = random.randint(60, 180)

    def update(self):
        if self.state == "enter":
            self.x += (self.tx - self.x) * 0.05
            self.y += (self.ty - self.y) * 0.05
            if abs(self.tx - self.x) < 2: self.state = "formation"
        elif self.state == "formation":
            self.shoot_timer -= 1
            if self.shoot_timer <= 0:
                self.shoot_timer = random.randint(100, 220)
                return Bullet(self.x, self.y + 15, 6, 1, RED)
            if random.random() < 0.001: self.state = "attack"
        elif self.state == "attack":
            self.y += 6
            self.x += math.sin(self.y * 0.04) * 5
            if self.y > HEIGHT: self.y = -50; self.state = "enter"
        return None

    def draw(self, s, offset):
        pygame.draw.polygon(s, RED, [
            (self.x + offset[0], self.y + 15 + offset[1]),
            (self.x - 13 + offset[0], self.y - 10 + offset[1]),
            (self.x + 13 + offset[0], self.y - 10 + offset[1])
        ])

    def get_rect(self):
        return pygame.Rect(self.x - 13, self.y - 10, 26, 25)


class Boss(GameObject):
    def __init__(self):
        super().__init__(WIDTH // 2, 100, GRAY)
        self.w, self.h = 160, 80
        self.hp = 300
        self.max_hp = 300
        self.timer = 0
        self.phase = 1
        self.phase_triggered = False
        self.pattern_timer = 0
        self.laser_rect = None
        self.laser_warning = False
        self.laser_x = 0

    def update(self):
        global shake_timer, shake_intensity, effects, enemies, player
        self.timer += 1
        self.pattern_timer += 1
        bullets = []
        self.x = (WIDTH // 2) + math.sin(self.timer * 0.02) * 150

        if self.hp < self.max_hp * 0.5 and not self.phase_triggered:
            self.phase = 2
            self.phase_triggered = True
            self.pattern_timer = 0
            effects.append(PhaseEffect(self.x, self.y))
            shake_timer, shake_intensity = 40, 15

        if self.phase == 1:
            if self.timer % 110 == 0: bullets += self.shoot_radial(16, 4)
            if self.timer % 70 == 0: bullets += self.shoot_aimed(6)
        else:
            cycle = self.pattern_timer % 420
            if cycle < 160:
                if self.timer % 45 == 0: bullets += self.shoot_radial(24, 5)
            elif cycle < 300:
                internal = cycle - 160
                if internal < 60:
                    self.laser_warning = True
                    self.laser_x = player.x
                else:
                    self.laser_warning = False
                    self.laser_rect = pygame.Rect(self.laser_x - 30, 0, 60, HEIGHT)
                    if internal % 8 == 0: shake_timer, shake_intensity = 5, 5
                if internal >= 130: self.laser_rect = None
            elif cycle < 420:
                if cycle == 301:
                    for _ in range(2):
                        en = FormationEnemy(self.x, self.y,
                                           random.randint(100, 800),
                                           random.randint(100, 300))
                        en.state = "attack"
                        enemies.append(en)
        return bullets

    def shoot_radial(self, count, speed):
        return [EnemyBullet(self.x, self.y,
                            math.cos(i * 2 * math.pi / count) * speed,
                            math.sin(i * 2 * math.pi / count) * speed)
                for i in range(count)]

    def shoot_aimed(self, speed):
        dx, dy = player.x - self.x, player.y - self.y
        dist = math.hypot(dx, dy) or 1
        return [EnemyBullet(self.x, self.y, dx / dist * speed, dy / dist * speed)]

    def draw(self, s, offset):
        ox, oy = self.x + offset[0], self.y + offset[1]
        fire_color = ORANGE if self.phase == 1 else RED
        for i in range(3):
            pygame.draw.circle(s, fire_color,
                               (int(ox - 50 + i * 50), int(oy - 30 + random.randint(0, 5))),
                               random.randint(10, 18))

        if self.phase == 1:
            pygame.draw.rect(s, DARK_GRAY, (ox - 90, oy - 20, 30, 50))
            pygame.draw.rect(s, DARK_GRAY, (ox + 60, oy - 20, 30, 50))
            pygame.draw.rect(s, GRAY, (ox - 60, oy - 40, 120, 80), 0, 10)
            pygame.draw.rect(s, BLACK, (ox - 40, oy - 10, 80, 20))
            pygame.draw.circle(s, CYAN, (int(ox), int(oy + 10)), 12)
        else:
            pygame.draw.rect(s, DARK_GRAY, (ox - 50, oy - 30, 100, 60))
            core_size = 25 + math.sin(self.timer * 0.2) * 5
            pygame.draw.circle(s, WHITE, (int(ox), int(oy)), int(core_size))
            pygame.draw.circle(s, RED, (int(ox), int(oy)), int(core_size), 4)
            pygame.draw.polygon(s, RED, [(ox - 30, oy - 15), (ox - 10, oy - 5), (ox - 35, oy - 5)])
            pygame.draw.polygon(s, RED, [(ox + 30, oy - 15), (ox + 10, oy - 5), (ox + 35, oy - 5)])
            if self.timer % 5 == 0:
                pygame.draw.line(s, YELLOW, (ox, oy),
                                 (ox + random.randint(-80, 80), oy + random.randint(-80, 80)), 2)

        if self.laser_warning:
            pygame.draw.line(s, RED, (self.laser_x + offset[0], 0),
                             (self.laser_x + offset[0], HEIGHT), 2)
        if self.laser_rect:
            pygame.draw.rect(s, WHITE, (self.laser_rect.x + offset[0], 0, self.laser_rect.w, HEIGHT))
            pygame.draw.rect(s, RED if self.phase == 2 else CYAN,
                             (self.laser_rect.x + 10 + offset[0], 0, self.laser_rect.w - 20, HEIGHT))

        pygame.draw.rect(s, BLACK, (ox - 80, oy - 70, 160, 12))
        pygame.draw.rect(s, RED, (ox - 80, oy - 70, 160 * (max(0, self.hp) / self.max_hp), 12))

    def get_rect(self):
        return pygame.Rect(self.x - 70, self.y - 40, 140, 80)


def create_wave(wave_num):
    enemies = []
    cols, rows = 8, min(5, 2 + wave_num)
    for r in range(rows):
        for c in range(cols):
            enemies.append(FormationEnemy(random.randint(0, 900), -50,
                                          120 + c * 90, 60 + r * 60))
    return enemies


player = Player(WIDTH // 2, HEIGHT - 80)
enemies, bullets, enemy_bullets, effects, lasers, shockwaves = create_wave(1), [], [], [], [], []
boss, wave, score, cooldown, machinegun_cd = None, 1, 0, 0, 0
upgrade_mode, game_over = False, False


async def main():
    global shake_timer, shake_intensity
    global player, enemies, bullets, enemy_bullets, effects, lasers, shockwaves
    global boss, wave, score, cooldown, machinegun_cd, upgrade_mode, game_over

    while True:
        clock.tick(60)
        if shake_timer > 0: shake_timer -= 1
        offset = apply_shake()

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN and not game_over:
                if upgrade_mode:
                    if e.key == pygame.K_1: player.max_hp += 1; player.hp += 1; upgrade_mode = False
                    if e.key == pygame.K_2: player.damage += 1; upgrade_mode = False
                    if e.key == pygame.K_3: player.speed += 1; upgrade_mode = False
                else:
                    if e.key == pygame.K_SPACE and cooldown == 0:
                        bullets += player.shoot()
                        cooldown = 12
                    if e.key == pygame.K_z and player.laser_gauge >= 50:
                        lasers.append(PlayerLaser(player.x))
                        player.laser_gauge -= 50
                    if e.key == pygame.K_c and player.laser_gauge >= 70:
                        shockwaves.append(Shockwave(player.x, player.y))
                        player.laser_gauge -= 70
            elif e.type == pygame.KEYDOWN and game_over and e.key == pygame.K_r:
                player = Player(WIDTH // 2, HEIGHT - 80)
                enemies, bullets, enemy_bullets, effects, lasers, shockwaves = create_wave(1), [], [], [], [], []
                boss, wave, score, game_over = None, 1, 0, False

        if not game_over and not upgrade_mode:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_x] and machinegun_cd == 0 and not player.reloading:
                if player.ammo > 0:
                    bullets.append(Bullet(player.x, player.y, -15, player.damage, ORANGE))
                    player.ammo -= 1
                    machinegun_cd = 4
                    if player.ammo <= 0:
                        player.reloading = True
                        player.reload_timer = 100
            if machinegun_cd > 0: machinegun_cd -= 1
            if cooldown > 0: cooldown -= 1

            player.update()
            if boss:
                bb = boss.update()
                if bb: enemy_bullets += bb
                if boss.hp <= 0:
                    effects.append(Explosion(boss.x, boss.y))
                    boss = None
                    wave += 1
                    upgrade_mode = True
                    enemies = create_wave(wave)

            for en in enemies:
                eb = en.update()
                if eb: enemy_bullets.append(eb)

            for b in bullets + enemy_bullets: b.update()
            for l in lasers: l.update()
            for s in shockwaves:
                s.update()
                for b in enemy_bullets[:]:
                    if math.hypot(b.x - s.x, b.y - s.y) < s.radius:
                        enemy_bullets.remove(b)

            p_rect = player.get_rect()
            for b in enemy_bullets:
                if b.get_rect().colliderect(p_rect) and player.invincible == 0:
                    player.hp -= 1
                    player.invincible = 60
                    effects.append(Explosion(player.x, player.y))
                    if player.hp <= 0: game_over = True
            if boss and boss.laser_rect and boss.laser_rect.colliderect(p_rect) and player.invincible == 0:
                player.hp -= 1
                player.invincible = 60
                effects.append(Explosion(player.x, player.y))
                if player.hp <= 0: game_over = True

            for b in bullets:
                if boss and b.get_rect().colliderect(boss.get_rect()):
                    boss.hp -= b.damage
                    b.alive = False
                    score += 5
                for en in enemies:
                    if b.get_rect().colliderect(en.get_rect()):
                        b.alive = False
                        en.alive = False
                        effects.append(Explosion(en.x, en.y))
                        score += 10

            enemies = [e for e in enemies if e.alive]
            bullets = [b for b in bullets if b.alive]
            enemy_bullets = [b for b in enemy_bullets if b.alive]
            lasers = [l for l in lasers if l.timer > 0]
            shockwaves = [s for s in shockwaves if s.alive]
            for ef in effects: ef.update()
            effects = [ef for ef in effects if ef.timer > 0]

            if not enemies and not boss and not upgrade_mode:
                boss = Boss()
                shake_timer, shake_intensity = 25, 12

        screen.fill(BLACK)
        for _ in range(10):
            pygame.draw.circle(screen, WHITE,
                               (random.randint(0, WIDTH), random.randint(0, HEIGHT)), 1)

        if not game_over:
            player.draw(screen, offset)
            for e in enemies: e.draw(screen, offset)
            for b in bullets + enemy_bullets: b.draw(screen, offset)
            for l in lasers: l.draw(screen, offset)
            for s in shockwaves: s.draw(screen, offset)
            for ef in effects: ef.draw(screen, offset)
            if boss: boss.draw(screen, offset)

            screen.blit(font.render(f"SCORE: {score}  WAVE: {wave}  HP: {player.hp}", True, WHITE), (15, 15))
            pygame.draw.rect(screen, DARK_GRAY, (15, 50, 150, 12))
            pygame.draw.rect(screen, CYAN, (15, 50, player.laser_gauge * 1.5, 12))
            ammo_txt = "RELOADING..." if player.reloading else f"AMMO: {player.ammo}"
            screen.blit(font.render(ammo_txt, True, ORANGE if player.reloading else YELLOW), (15, 70))

            if upgrade_mode:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 200))
                screen.blit(overlay, (0, 0))
                txt = font.render("MISSION CLEAR! CHOOSE UPGRADE: 1.HP  2.DMG  3.SPEED", True, WHITE)
                screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2))
        else:
            msg = big_font.render("GAME OVER", True, RED)
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 50))
            info = font.render(f"FINAL SCORE: {score} | PRESS 'R' TO RESTART", True, WHITE)
            screen.blit(info, (WIDTH // 2 - info.get_width() // 2, HEIGHT // 2 + 40))

        pygame.display.flip()
        await asyncio.sleep(0)


asyncio.run(main())
