import random

import pygame
pygame.init()

FPS =60
WIDTH = 1000
HEIGHT = 600
background_color = (140, 140, 140)

menu_background = pygame.image.load("menu_background.png")
menu_background = pygame.transform.scale(menu_background, (WIDTH, HEIGHT))

game_background = pygame.image.load("game_background.png")
game_background = pygame.transform.scale(game_background, (WIDTH, HEIGHT))

top_players_background = pygame.image.load("top_players_background.png")
top_players_background = pygame.transform.scale(top_players_background, (WIDTH, HEIGHT))

player = pygame.image.load("player.png")
player = pygame.transform.scale(player, (100, 100))
player_rect = player.get_rect()
player_rect.left = 400
player_rect.top = 500

back_button = pygame.image.load("back_button.png")
back_button_rect = back_button.get_rect()
back_button_rect.left = 0
back_button_rect.top = 500

start_game_button = pygame.Rect(390, 115, 245, 40)
exit_button = pygame.Rect(460, 472, 100, 40)
top_players_button = pygame.Rect(390, 195, 245, 40)
secret_button = pygame.Rect(0, 0, 10, 10)

window = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

heart_image = pygame.image.load("heart.png")
heart_image = pygame.transform.scale(heart_image, (40, 40))
hearts = 3

pumpkin = pygame.image.load("pumpkin.png")
pumpkin = pygame.transform.scale(pumpkin, (100, 100))

pumpkin1_rect = pumpkin.get_rect()
pumpkin1_rect.x = random.randint(0, WIDTH - 100)
pumpkin1_rect.y = random.randint(-600, -50)

pumpkin2_rect = pumpkin.get_rect()
pumpkin2_rect.x = random.randint(0, WIDTH - 100)
pumpkin2_rect.y = random.randint(-600, -50)

pumpkin3_rect = pumpkin.get_rect()
pumpkin3_rect.x = random.randint(0, WIDTH - 100)
pumpkin3_rect.y = random.randint(-600, -50)

speed1 = 2
speed2 = 3
speed3 = 4

gamemode = "menu"
run = True

game_start_time = 0
game_over_time = 0
game_font = pygame.font.Font(None, 50)
timer_font = pygame.font.Font(None, 40)

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def resource_path(*parts: str) -> str:
    return os.path.join(BASE_DIR, *parts)

game_sound_1 = pygame.mixer.Sound(resource_path("music", "main_theme1.wav"))
game_sound_2 = pygame.mixer.Sound(resource_path("music", "main_theme2.mp3"))
game_sound_3 = pygame.mixer.Sound(resource_path("music", "main_theme3.mp3"))
game_sound_4 = pygame.mixer.Sound(resource_path("music", "main_theme4.mp3"))
game_sound_5 = pygame.mixer.Sound(resource_path("music", "main_theme5.mp3"))
game_sound_6 = pygame.mixer.Sound(resource_path("music", "main_theme6.mp3"))

play_list = [game_sound_1, game_sound_2, game_sound_3, game_sound_4, game_sound_5, game_sound_6]
current_music = random.choice(play_list)
current_music.set_volume(0.1)
current_music.play(loops=-1)

while run:
    if gamemode == "menu":
        window.blit(menu_background, (0, 0))
        for i in pygame.event.get():
            if i.type == pygame.QUIT:
                run = False
            if i.type == pygame.MOUSEBUTTONDOWN:
                if i.button == 1:
                    if start_game_button.collidepoint(i.pos):
                        gamemode = "game"
                        game_start_time = pygame.time.get_ticks()
                    if exit_button.collidepoint(i.pos):
                        run = False
                    if top_players_button.collidepoint(i.pos):
                        gamemode = "top_players"


        # pygame.draw.rect(window, (0, 200, 0), top_players_button)

    if gamemode == "game":
        window.blit(game_background, (0, 0))

        for i in pygame.event.get():
            if i.type == pygame.QUIT:
                run = False
            if i.type == pygame.MOUSEBUTTONDOWN:
                if pumpkin1_rect.collidepoint(i.pos):
                    pumpkin1_rect.x = random.randint(0, WIDTH - 100)
                    pumpkin1_rect.y = -50
                if pumpkin2_rect.collidepoint(i.pos):
                    pumpkin2_rect.x = random.randint(0, WIDTH - 100)
                    pumpkin2_rect.y = -50
                if pumpkin3_rect.collidepoint(i.pos):
                    pumpkin3_rect.x = random.randint(0, WIDTH - 100)
                    pumpkin3_rect.y = -50
                if back_button_rect.collidepoint(i.pos):
                    gamemode = "menu"
                if secret_button.collidepoint(i.pos):
                    if hearts < 3:
                        hearts += 1

        # узнаём, какие клавиши сейчас зажаты
        keys = pygame.key.get_pressed()

        if keys[pygame.K_d]:
            player_rect.left += 5
        if keys[pygame.K_a]:
            player_rect.left -= 5
        if keys[pygame.K_s]:
            player_rect.top += 5
        if keys[pygame.K_w]:
            player_rect.top -= 5
        if keys[pygame.K_r]:
            player_rect.top = 200
            player_rect.left = 400

        # не выходим за края
        if player_rect.left < 0:
            player_rect.left = 0
        if player_rect.right > WIDTH:
            player_rect.right = WIDTH
        if player_rect.top < 0:
            player_rect.top = 0
        if player_rect.bottom > HEIGHT:
            player_rect.bottom = HEIGHT

        pumpkin1_rect.y += speed1
        pumpkin2_rect.y += speed2
        pumpkin3_rect.y += speed3

        speed1 += 0.0005
        speed2 += 0.0005
        speed3 += 0.0005

        if pumpkin1_rect.top > HEIGHT:
            pumpkin1_rect.x = random.randint(0, WIDTH - 100)
            pumpkin1_rect.y = -50
        if pumpkin2_rect.top > HEIGHT:
            pumpkin2_rect.x = random.randint(0, WIDTH - 100)
            pumpkin2_rect.y = -50
        if pumpkin3_rect.top > HEIGHT:
            pumpkin3_rect.x = random.randint(0, WIDTH - 100)
            pumpkin3_rect.y = -50

        if player_rect.colliderect(pumpkin1_rect):
            pumpkin1_rect.x = random.randint(0, WIDTH - 100)
            pumpkin1_rect.y = -50
            hearts -= 1
        if player_rect.colliderect(pumpkin2_rect):
            pumpkin2_rect.x = random.randint(0, WIDTH - 100)
            pumpkin2_rect.y = -50
            hearts -= 1
        if player_rect.colliderect(pumpkin3_rect):
            pumpkin3_rect.x = random.randint(0, WIDTH - 100)
            pumpkin3_rect.y = -50
            hearts -= 1

        for i in range(hearts):
            window.blit(heart_image, (850 + i * 50, 10))

        current_time = (pygame.time.get_ticks() - game_start_time) // 1000
        timer_text = timer_font.render(f"{current_time} сек.", True, (255, 255, 255))
        window.blit(timer_text, (WIDTH - timer_text.get_width() - 20, HEIGHT - timer_text.get_height() - 20))

        if hearts == 0:
            hearts = 3
            game_over_time = (pygame.time.get_ticks() - game_start_time) // 1000
            gamemode = "gameover"

        window.blit(pumpkin, pumpkin1_rect)
        window.blit(pumpkin, pumpkin2_rect)
        window.blit(pumpkin, pumpkin3_rect)

        window.blit(back_button, (0, 520))
        window.blit(player, player_rect)

    if gamemode == "gameover":
        window.fill((200, 0, 0))

        for i in pygame.event.get():
            if i.type == pygame.QUIT:
                run = False
            if i.type == pygame.MOUSEBUTTONDOWN:
                if i.button == 1:
                    if back_button_rect.collidepoint(i.pos):
                        gamemode = "menu"

        result_text = game_font.render(f"Вы продержались: {game_over_time} сек.", True, (255, 255, 255))
        window.blit(result_text, (WIDTH // 2 - result_text.get_width() // 2, 250))

        window.blit(back_button, (0, 520))

    if gamemode == "top_players":
        window.blit(top_players_background, (0, 0))
        for i in pygame.event.get():
            if i.type == pygame.QUIT:
                run = False
            if i.type == pygame.MOUSEBUTTONDOWN:
                if i.button == 1:
                    if back_button_rect.collidepoint(i.pos):
                        gamemode = "menu"

        window.blit(back_button, (0, 520))


    pygame.display.update()
    clock.tick(FPS)
pygame.quit()