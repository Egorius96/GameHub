import os
import random
from datetime import datetime, timezone, timedelta


import pygame
import httpx


cars_speed = {1: 3, 2: 6, 3: 10}
cars_costs = {1: 0, 2: 20, 3: 100}

lives = 3
lives2 = 3
speed_rock = 10.0
first_player_direction = "stop"
second_player_direction = "stop"

db_url_sign_in = "http://94.159.100.3:7998/users/auth"
db_url_register = "http://94.159.100.3:7998/users/"

width = 1200
height = 700
fps = 60

gamemode = "login"

user = None
users_records = None
current_car = None
current_car_rect = None
player_1_car = None
player_1_car_rect = None
player_2_car = None
player_2_car_rect = None

game_over_winner = None
game_over_seconds = 0

diamond_cooldown = 0
DIAMOND_COOLDOWN_FRAMES = 180

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts: str) -> str:
    return os.path.join(BASE_DIR, *parts)


pygame.init()
pygame.mixer.init()
pg = pygame
clock = pg.time.Clock()
sc = pg.display.set_mode((width, height))

car_LVL_1 = pg.image.load(resource_path("pictures", "car_lvl1.png"))
car_LVL_1 = pg.transform.scale(car_LVL_1, (150, 68))
car_LVL_1_shield = pg.image.load(resource_path("pictures", "car_lvl1_shield.png"))
car_LVL_1_shield = pg.transform.scale(car_LVL_1_shield, (150, 68))

car_LVL_2 = pg.image.load(resource_path("pictures", "car_lvl2.png"))
car_LVL_2 = pg.transform.scale(car_LVL_2, (150, 68))
car_LVL_2_shield = pg.image.load(resource_path("pictures", "car_lvl2_shield.png"))
car_LVL_2_shield = pg.transform.scale(car_LVL_2_shield, (150, 68))

car_LVL_3 = pg.image.load(resource_path("pictures", "car_lvl3.png"))
car_LVL_3 = pg.transform.scale(car_LVL_3, (150, 68))
car_LVL_3_shield = pg.image.load(resource_path("pictures", "car_lvl3_shield.png"))
car_LVL_3_shield = pg.transform.scale(car_LVL_3_shield, (150, 68))

rock = pg.image.load(resource_path("pictures", "rock.png"))
rock = pg.transform.scale(rock, (100, 80))

diamond = pg.image.load(resource_path("pictures", "brilliant.png"))
diamond = pg.transform.scale(diamond, (100, 60))
small_diamond = pg.transform.scale(diamond, (50, 30))

heart = pg.image.load(resource_path("pictures", "heart.png"))
heart = pg.transform.scale(heart, (50, 50))

menu_background = pg.image.load(resource_path("pictures", "menu_background.png"))
login_background = pg.image.load(resource_path("pictures", "login_background.png"))
settings_background = pg.image.load(resource_path("pictures", "settings_background.png"))
game_background = pg.image.load(resource_path("pictures", "game_background.jpg"))
game_background = pg.transform.scale(game_background, (1200, 700))
super_background = pg.image.load(resource_path("pictures", "super background.webp"))
super_background = pg.transform.scale(super_background, (1200, 700))

exit_button = pg.image.load(resource_path("pictures", "exit_button.png"))
exit_button_rect = exit_button.get_rect(topleft=(500, 500))

register_button = pg.image.load(resource_path("pictures", "register_btn.png"))
register_button = pg.transform.scale(register_button, (100, 50))
register_button_rect = register_button.get_rect(topleft=(400, 400))

settings_button = pg.image.load(resource_path("pictures", "store.png"))
settings_button_rect = settings_button.get_rect(topleft=(150, 450))

start_button = pg.image.load(resource_path("pictures", "start_button.png"))
start_button_rect = start_button.get_rect(topleft=(900, 500))
start_button2 = pg.image.load(resource_path("pictures", "start_button.png"))
start_button_rect2 = start_button2.get_rect(topleft=(900, 300))

leaderboard_button = pg.image.load(resource_path("pictures", "champions_btn.png"))
leaderboard_button_rect = leaderboard_button.get_rect(topleft=(450, 400))

cancel_button = pg.image.load(resource_path("pictures", "cancel_btn.png"))
cancel_button_rect = cancel_button.get_rect(topleft=(500, 500))

upgrade_button = pg.image.load(resource_path("pictures", "upgrade_button.png"))
upgrade_button = pg.transform.scale(upgrade_button, (200, 100))
upgrade_button_rect = upgrade_button.get_rect(topleft=(800, 500))
superpowers_button = pg.image.load(resource_path("pictures", "superpowers.png"))
superpowers_button = pg.transform.scale(superpowers_button, (200, 100))
superpowers_button_rect = superpowers_button.get_rect(topleft=(300, 500))

rock_rect_1 = rock.get_rect()
rock_rect_2 = rock.get_rect()
diamond_rect = diamond.get_rect()

drugs_image = pg.image.load(resource_path("pictures", "drugs.png"))
drugs_image = pg.transform.scale(drugs_image, (50,50 ))
sheild_image = pg.image.load(resource_path("pictures", "sheild.png"))
sheild_image = pg.transform.scale(sheild_image, (50,50 ))
timer_image = pg.image.load(resource_path("pictures", "timer.png"))
timer_image = pg.transform.scale(timer_image, (50,50 ))
rockheart_image = pg.image.load(resource_path("pictures", "heartrock.png"))
rockheart_image = pg.transform.scale(rockheart_image, (50,50 ))

drugs_button = pg.image.load(resource_path("pictures", "drugs.png"))
drugs_button = pg.transform.scale(drugs_button, (100,100 ))
drugs_button_rect = drugs_button.get_rect(topleft=(200, 500))
sheild_button = pg.image.load(resource_path("pictures", "sheild.png"))
sheild_button = pg.transform.scale(sheild_button, (100,100 ))
sheild_button_rect = sheild_button.get_rect(topleft=(350, 500))
timer_button = pg.image.load(resource_path("pictures", "timer.png"))
timer_button = pg.transform.scale(timer_button, (100,100 ))
timer_button_rect = timer_button.get_rect(topleft=(950, 500))
rockheart_button = pg.image.load(resource_path("pictures", "heartrock.png"))
rockheart_button = pg.transform.scale(rockheart_button, (100,100 ))
rockheart_button_rect = rockheart_button.get_rect(topleft=(800, 500))
hard_button = pg.image.load(resource_path("pictures", "hard.png"))
hard_button = pg.transform.scale(hard_button, (200,100 ))
hard_button_rect = hard_button.get_rect(topleft=(150, 250))
road = []
for i in range(1, width, 230):
    road.append([i, 335, 150, 25])

font_login = pygame.font.SysFont("georgia", 30)

user_name_input_box = pygame.Rect(450, 280, 335, 45)
password_input_box = pygame.Rect(450, 338, 335, 45)
sign_in_button = pygame.Rect(710, 407, 70, 40)

user_name_active = False
password_active = False
user_name_text = ''
password_text = ''
label_auth_err_bool = False
label_register_bool = False
label_server_err_bool = False
label_empty_fields_bool = False
label_invalid_spaces_bool = False
label_auth_err = font_login.render("User not found, please register :)", True, (255, 0, 32))
label_register = font_login.render("user sucssesfully created :)", True, (255, 0, 32))
label_server_err = font_login.render("Server unavailable, try again later", True, (255, 0, 32))
label_empty_fields = font_login.render("Username and password are required", True, (255, 0, 32))
label_invalid_spaces = font_login.render("Invalid characters in username or password", True, (255, 0, 32))
label_notenough = ""
label_car = font_login.render("", True, (255, 0, 32))

pvp_hint_visible = False

color_inactive = pygame.Color("gray")
color_active = pygame.Color('dodgerblue2')

main_theme = pygame.mixer.Sound(resource_path("music", "main_theme.wav"))
main_theme.set_volume(0.1)
main_theme_2 = pygame.mixer.Sound(resource_path("music", "main_theme_2.mp3"))
main_theme_2.set_volume(0.3)
main_theme_list = [main_theme, main_theme_2]
game_sound_1 = pygame.mixer.Sound(resource_path("music", "game_sound_1.mp3"))
game_sound_1.set_volume(0.1)
game_sound_2 = pygame.mixer.Sound(resource_path("music", "game_sound_2.mp3"))
game_sound_2.set_volume(0.1)
game_sound_3 = pygame.mixer.Sound(resource_path("music", "game_sound_3.mp3"))
game_sound_3.set_volume(0.1)
game_sound_4 = pygame.mixer.Sound(resource_path("music", "game_sound_4.mp3"))
game_sound_4.set_volume(0.1)
game_sound_5 = pygame.mixer.Sound(resource_path("music", "game_sound_5.wav"))
game_sound_5.set_volume(0.1)
game_sound_6 = pygame.mixer.Sound(resource_path("music", "game_sound_6.mp3"))
game_sound_6.set_volume(0.1)
music_list = [game_sound_1, game_sound_2, game_sound_3, game_sound_5, game_sound_6]

gameover_sound = pygame.mixer.Sound(resource_path("music", "gameover.mp3"))
diamond_sound = pygame.mixer.Sound(resource_path("music", "diamond.mp3"))
rock_sound = pygame.mixer.Sound(resource_path("music", "rockhit.mp3"))

purchase_sound = pygame.mixer.Sound(resource_path("music", "purchase.mp3"))
button_sound = pygame.mixer.Sound(resource_path("music", "button.mp3"))
drugs_sound = pygame.mixer.Sound(resource_path("music", "drugs.wav"))
immue_sound = pygame.mixer.Sound(resource_path("music", "immue.wav"))
rockspeed_sound = pygame.mixer.Sound(resource_path("music", "rockspeed.mp3"))
rockheart_sound = pygame.mixer.Sound(resource_path("music", "rockheart.wav"))

rockhit_2 = {"rockhit_2": False}
start_1hp = {"start_1hp": False}
diamond_no = {"diamond_no": False}
not_level = {"not_level": False}
no_super = {"no_super": False}
rocks_sec = {"rocks_sec": False}
rocks_acs = {"rocks_acs": False}
big_car = {"big_car": False}
inverted_move = {"inverted_move": False}
low_diam = {"low_diam": False}
modifiers = [rockhit_2, start_1hp, diamond_no, not_level, no_super, rocks_sec, rocks_acs, big_car, inverted_move, low_diam]


MODIFIER_KEYS = (
    "rockhit_2",
    "start_1hp",
    "diamond_no",
    "not_level",
    "no_super",
    "rocks_sec",
    "rocks_acs",
    "big_car",
    "inverted_move",
    "low_diam",
)

headers = {"accept": "application/json", "Content-Type": "application/json"}


def safe_post(url: str, payload: dict):
    try:
        with httpx.Client(timeout=5.0) as client:
            return client.post(url, headers=headers, json=payload)
    except httpx.RequestError:
        return None


def safe_put(url: str, payload: dict):
    try:
        with httpx.Client(timeout=5.0) as client:
            client.put(url, headers=headers, json=payload)
    except httpx.RequestError:
        pass


def auth(username, password):
    response = safe_post(
        db_url_sign_in,
        {"username": username, "password": password},
    )
    if response is None:
        return {"error": "connection"}
    data = response.json()
    if data.get("username"):
        other = data.setdefault("other_data", {})
        other["last_login_at"] = datetime.now(timezone.utc).isoformat()
        save_user(data)
    return data


def register_user(username, password):
    register_data = {
        "username": username,
        "password": password,
        "project": "pro_racing_game",
        "other_data": {
            "diamonds": 0,
            "car_level": 1,
            "two_players_gamemode": False,
            "matches_count": 0,
            "high_score_seconds": 0,
            "superpowers": {
                "drugs": False,
                "immue": False,
                "time_stop": False,
                "minigun": False,
                "rockspeed": False,
                "hearty_rock": False,
            },

            "last_login_at": datetime.now(timezone.utc).isoformat()
        }
    }
    response = safe_post(db_url_register, register_data)
    if response is None:
        return {"error": "connection"}
    return response.json()


def save_user(user):
    data = {
        "user_auth": {"username": user["username"], "password": user["password"]},
        "user_update": {
            "username": user["username"],
            "password": user["password"],
            "project": "pro_racing_game",
            "other_data": user["other_data"],
        }
    }
    safe_put(f"{db_url_register}update", data)

def cancel_btn():
    global gamemode
    gamemode = "menu"
    button_sound.play()

run = True
seconds = 0
frame_count = 0

current_theme = random.choice(main_theme_list)
current_theme.set_volume(0.1)
current_theme.play(loops=-1)

immue_last_use_time =  datetime.now() - timedelta(seconds=60)
immue = False
hearty_last_use_time =  datetime.now() - timedelta(seconds=40)
hearty = False
superpowers_parameters = {
    "drugs": {
        "game_limit": 5,
        "cost": 50
    },
    "immue": {
        "cooldown": 60,
        "last_use": datetime,
        "duration": 10,
        "cost": 200
    },
    "time_stop": {},
    "minigun": {},
    "rockspeed": {
        "game_limit": 1,
        "cost": 300,
    },
    "hearty_rock":{
        "cooldown": 40,
        "cost": 100
    },
}
label_drugs_cost = font_login.render(f"{superpowers_parameters['drugs']['cost']}", True, (255, 255, 255))
label_immue_cost = font_login.render(f"{superpowers_parameters['immue']['cost']}", True, (255, 255, 255))
label_timer_cost = font_login.render(f"{superpowers_parameters['rockspeed']['cost']}", True, (255, 255, 255))
label_heartrock_cost = font_login.render(f"{superpowers_parameters['hearty_rock']['cost']}", True, (255, 255, 255))

label_drugs_true = font_login.render(f"drugs: yes", True, (0, 0, 255))
label_immue_true = font_login.render(f"immue: yes", True, (0, 0, 255))
label_rockspeed_true = font_login.render(f"rock slowdown: yes", True, (0, 0, 255))
label_rockheart_true = font_login.render(f"hearty rock: yes", True, (0, 0, 255))

label_drugs_false = font_login.render(f"drugs: no", True, (0, 0, 255))
label_immue_false = font_login.render(f"immue: no", True, (0, 0, 255))
label_rockspeed_false = font_login.render(f"rock slowdown: no", True, (0, 0, 255))
label_rockheart_false = font_login.render(f"hearty rock: no", True, (0, 0, 255))

label_drugs_how = font_login.render("if you press e you are gonna lose one heart but get 10 seconds to stopwatch (use per game: 5)", True, (255, 255, 255))
label_immue_how = font_login.render("if you press q you are gonna recieve a sheild for 5 seconds"
                                    " not obtaining damage at all(cooldown: 60)", True, (255, 255, 255))
label_rockspeed_how = font_login.render("if you press r all rocks are gonna fly with normal speed(use per game: 1)", True, (255, 255, 255))
label_rockheart_how = font_login.render("if you press t next rock is gonna give u 1 hp(cd.: 40)", True, (255, 255, 255))
while run:
    if gamemode == "menu" and user is not None:
        label_welcome = font_login.render(f"Welcome, {user['username']}!", True, (255, 220, 100))
        label_diamonds = font_login.render(f"Diamonds: {user['other_data']['diamonds']}", True, (200, 255, 200))
        #main_theme.play()
        desc1 = font_login.render("• Hit rock -> lose 1 life", True, (255, 180, 180))
        desc2 = font_login.render("• Catch diamond -> +1 life & + 1 diamond", True, (180, 255, 180))
        desc3 = font_login.render("Survive as long as possible!", True, (220, 220, 255))

        for i in pg.event.get():
            if i.type == pg.QUIT:
                save_user(user)
                run = False
                if user:
                    save_user(user)
            if i.type == pygame.MOUSEBUTTONDOWN and i.button == 1:
                if exit_button_rect.collidepoint(i.pos):
                    button_sound.play()
                    pvp_hint_visible = False
                    gamemode = "login"
                    if user:
                        save_user(user)
                elif hard_button_rect.collidepoint(i.pos):
                    button_sound.play()
                    gamemode = "hard"
                    level = user["other_data"]["car_level"]
                    if user:
                        save_user(user)
                    if level == 1:
                        current_car = car_LVL_1
                    elif level == 2:
                        current_car = car_LVL_2
                    else:
                        current_car = car_LVL_3
                    current_car_rect = current_car.get_rect()
                    current_car_rect.left = 50
                    current_car_rect.top = 300
                    current_mus = random.choice(music_list)
                    current_mus.set_volume(0.1)
                    current_mus.play(loops=-1)
                elif settings_button_rect.collidepoint(i.pos):
                    button_sound.play()
                    pvp_hint_visible = False
                    gamemode = "settings"
                elif start_button_rect.collidepoint(i.pos):
                    button_sound.play()
                    pvp_hint_visible = False
                    gamemode = "game"
                    level = user["other_data"]["car_level"]
                    if level == 1:
                        current_car = car_LVL_1
                    elif level == 2:
                        current_car = car_LVL_2
                    else:
                        current_car = car_LVL_3
                    current_car_rect = current_car.get_rect()
                    current_car_rect.left = 50
                    current_car_rect.top = 300
                    speed_rock = 10.0
                    lives = 3
                    seconds = 0
                    frame_count = 0
                    first_player_direction = "stop"
                    rock_rect_1.left = 1200
                    rock_rect_1.top = random.randint(0, 650)
                    rock_rect_2.left = 1900
                    rock_rect_2.top = random.randint(0, 650)
                    diamond_rect.left = 1400
                    diamond_cooldown = 0
                    current_mus = random.choice(music_list)
                    current_mus.set_volume(0.1)
                    current_mus.play(loops=-1)
                elif start_button_rect2.collidepoint(i.pos):
                    button_sound.play()
                    level = user["other_data"]["car_level"]
                    if level >= 3:
                        pvp_hint_visible = False
                        gamemode = "game2"
                        car_img = car_LVL_1 if level == 1 else car_LVL_2 if level == 2 else car_LVL_3
                        player_1_car = car_img
                        player_1_car_rect = car_img.get_rect()
                        player_1_car_rect.left = 50
                        player_1_car_rect.top = 100
                        player_2_car = car_img
                        player_2_car_rect = car_img.get_rect()
                        player_2_car_rect.left = 50
                        player_2_car_rect.top = 450
                        speed_rock = 10.0
                        lives = 3
                        lives2 = 3
                        seconds = 0
                        frame_count = 0
                        first_player_direction = "stop"
                        second_player_direction = "stop"
                        rock_rect_1.left = 1200
                        rock_rect_1.top = random.randint(0, 250)
                        rock_rect_2.left = 1900
                        rock_rect_2.top = random.randint(300, 650)
                        diamond_rect.left = 1400
                        current_mus = random.choice(music_list)
                        current_mus.set_volume(0.1)
                        current_mus.play(loops=-1)
                    else:
                        pvp_hint_visible = True
                elif leaderboard_button_rect.collidepoint(i.pos):
                    button_sound.play()
                    pvp_hint_visible = False
                    gamemode = "leader"
        sc.blit(menu_background, (0, 0))

        center_x = width // 2

        sc.blit(label_welcome, (center_x - label_welcome.get_width() // 2, 60))
        sc.blit(label_diamonds, (center_x - label_diamonds.get_width() // 2, 100))

        sc.blit(desc1, (center_x - desc1.get_width() // 2, 160))
        sc.blit(desc2, (center_x - desc2.get_width() // 2, 195))
        sc.blit(desc3, (center_x - desc3.get_width() // 2, 230))

        if pvp_hint_visible:
            pvp_hint = font_login.render("PVP mode unlocks at car level 3", True, (255, 0, 50))
            sc.blit(pvp_hint, (750, 400))

        sc.blit(exit_button, (500, 500))
        sc.blit(settings_button, (150, 450))
        sc.blit(start_button, (900, 500))
        sc.blit(hard_button, (150, 250))

        pvp_rect = pygame.Rect(900, 300, 280, 80)
        pygame.draw.rect(sc, (60, 100, 180), pvp_rect, border_radius=12)
        pygame.draw.rect(sc, (100, 140, 220), pvp_rect, 4, border_radius=12)

        pvp_text = font_login.render("PVP with friend", True, (255, 255, 255))
        sc.blit(pvp_text, (pvp_rect.centerx - pvp_text.get_width() // 2,
                           pvp_rect.centery - pvp_text.get_height() // 2))

        sc.blit(leaderboard_button, (450, 400))

    elif gamemode == "game" and user is not None:
        main_theme.stop()
        main_theme_2.stop()
        sc.blit(game_background, (0, 0))
        frame_count += 1
        if frame_count >= 60:
            seconds += 1
            frame_count = 0
            speed_rock += 0.1

        for event in pg.event.get():
            if event.type == pg.QUIT:
                save_user(user)
                run = False

            elif event.type == pg.KEYDOWN:
                if event.key in (pg.K_w, pg.K_UP): first_player_direction = "up"
                elif event.key in (pg.K_s, pg.K_DOWN): first_player_direction = "down"
                elif event.key in (pg.K_a, pg.K_LEFT): first_player_direction = "left"
                elif event.key in (pg.K_d, pg.K_RIGHT): first_player_direction = "right"

                elif event.key == pg.K_e and lives != 1 and user['other_data']['superpowers']['drugs']:
                    if user["other_data"]["superpowers"]["drugs"]:
                        if superpowers_parameters["drugs"]["game_limit"] > 0:
                            superpowers_parameters["drugs"]["game_limit"] -= 1
                            seconds += 10
                            lives -= 1
                            drugs_sound.play()
                elif event.key == pg.K_q and user['other_data']['superpowers']['immue']:
                    if (datetime.now() - immue_last_use_time).total_seconds() >= superpowers_parameters['immue']['cooldown']:
                        immue_sound.play()
                        immue_last_use_time = datetime.now()
                        immue = True
                        if current_car == car_LVL_1:
                            current_car = car_LVL_1_shield
                        elif current_car == car_LVL_2:
                            current_car = car_LVL_2_shield
                        elif current_car == car_LVL_3:
                            current_car = car_LVL_3_shield
                elif event.key == pg.K_r and user['other_data']['superpowers']['rockspeed']:
                    if superpowers_parameters["rockspeed"]["game_limit"] > 0:
                        superpowers_parameters["rockspeed"]["game_limit"] -= 1
                        speed_rock = 10.0
                        rockspeed_sound.play()
                elif event.key == pg.K_t and user["other_data"]["superpowers"]["hearty_rock"]:
                    if (datetime.now() - hearty_last_use_time).total_seconds() >= 40:
                        hearty_last_use_time = datetime.now()
                        hearty = True
                        rockheart_sound.play()

        if (datetime.now() - immue_last_use_time).total_seconds() >= 10:
            immue = False
            if current_car == car_LVL_1_shield:
                current_car = car_LVL_1
            elif current_car == car_LVL_2_shield:
                current_car = car_LVL_2
            elif current_car == car_LVL_3_shield:
                current_car = car_LVL_3


        level_speed = cars_speed[user["other_data"]["car_level"]]
        if first_player_direction == "up" and current_car_rect.top > 0:
            current_car_rect.top -= level_speed
        elif first_player_direction == "down" and current_car_rect.top < 635:
            current_car_rect.top += level_speed
        elif first_player_direction == "right" and current_car_rect.right < 1200:
            current_car_rect.right += 5
        elif first_player_direction == "left" and current_car_rect.right > 150:
            current_car_rect.right -= 5

        for i in road:
            if i[0] < -150:
                i[0] = width
            i[0] -= 2
            pg.draw.rect(sc, (255, 255, 255), i)

        if rock_rect_1.right > -100:
            sc.blit(rock, rock_rect_1)
            rock_rect_1.right -= speed_rock
        else:
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)

        if rock_rect_2.right > -100:
            sc.blit(rock, rock_rect_2)
            rock_rect_2.right -= speed_rock
        else:
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)

        if diamond_cooldown > 0:
            diamond_cooldown -= 1
        else:
            if diamond_rect.right <= -100:
                if random.random() < 0.004:
                    diamond_rect.left = random.randint(1200, 1600)
                    diamond_rect.top = random.randint(0, 650)
            else:
                sc.blit(diamond, diamond_rect)
                diamond_rect.right -= 25

        sc.blit(current_car, current_car_rect)

        if current_car_rect.colliderect(rock_rect_1) and immue == False and hearty == False:
            lives -= 1
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_1) and hearty == True:
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)
            lives += 1
            hearty = False
            diamond_sound.play()
        if current_car_rect.colliderect(rock_rect_2) and immue == False and hearty == False:
            lives -= 1
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_2) and hearty == True:
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)
            lives += 1
            hearty = False
            diamond_sound.play()
        if current_car_rect.colliderect(diamond_rect):
            lives += 1
            user["other_data"]["diamonds"] += 1
            diamond_rect.right = -100
            diamond_cooldown = DIAMOND_COOLDOWN_FRAMES
            diamond_sound.play()
        if lives < 1:
            gameover_sound.play()
            if seconds > user["other_data"]["high_score_seconds"]:
                user["other_data"]["high_score_seconds"] = seconds
            user["other_data"]["matches_count"] += 1
            save_user(user)
            gamemode = "gameover"
            lives = 3

            frame_count = 0
            first_player_direction = "stop"
            current_mus.stop()
            current_theme = random.choice(main_theme_list)
            current_theme.set_volume(0.5)
            current_theme.play(loops=-1)
            superpowers_parameters['drugs']['game_limit'] = 5
            superpowers_parameters['rockspeed']['game_limit'] = 1
        for i in range(lives):
            sc.blit(heart, (i * 60, 10))
        sc.blit(small_diamond, (1050, 600))
        diamond_text = font_login.render(str(user['other_data']['diamonds']), True, (255, 0, 32))
        sc.blit(diamond_text, (1105, 605))
        seconds_text = font_login.render(f"{seconds} sec", True, (255, 0, 32))
        sc.blit(seconds_text, (1050, 640))
        if user['other_data']['superpowers']['drugs']:
            sc.blit(drugs_image, (950, 595))
        if user['other_data']['superpowers']['immue']:
            sc.blit(sheild_image, (850, 595))
        if user['other_data']['superpowers']['rockspeed']:
            sc.blit(timer_image, (850, 645))
        if user['other_data']['superpowers']['hearty_rock']:
            sc.blit(rockheart_image, (950,645))
        label_drugs_use = font_login.render(f"{superpowers_parameters['drugs']['game_limit']}", True,(255, 0, 32))
        label_rockspeed_use = font_login.render(f"{superpowers_parameters['rockspeed']['game_limit']}", True,(255, 0, 32))
        immue_cooldown = int(60 - ((datetime.now() - immue_last_use_time).total_seconds()))
        if immue_cooldown <= 0:
            label_immue_seconds = font_login.render("0", True, (255, 0, 32))
        else:
            label_immue_seconds = font_login.render(f"{immue_cooldown}", True, (255, 0, 32))
        rockheart_cooldown = int(40 - ((datetime.now() - hearty_last_use_time).total_seconds()))
        if rockheart_cooldown <= 0:
            label_rockheart_seconds = font_login.render("0", True, (255, 0, 32))
        else:
            label_rockheart_seconds = font_login.render(f"{rockheart_cooldown}", True, (255, 0, 32))
        if user['other_data']['superpowers']['drugs']:
            sc.blit(label_drugs_use, (1000,595))
        if user['other_data']['superpowers']['rockspeed']:
            sc.blit(label_rockspeed_use, (900, 645))
        if user['other_data']['superpowers']['immue']:
            sc.blit(label_immue_seconds, (900, 595))
        if user['other_data']['superpowers']['hearty_rock']:
            sc.blit(label_rockheart_seconds, (1000, 645))
    elif gamemode == "gameover" and user is not None:
        sc.blit(game_background, (0, 0))

        overlay = pygame.Surface((width, height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        sc.blit(overlay, (0, 0))

        game_over_text = font_login.render("GAME OVER", True, (255, 100, 100))
        sc.blit(game_over_text, (width // 2 - game_over_text.get_width() // 2, 120))

        time_text = font_login.render(f"Survived: {seconds} seconds", True, (255, 255, 200))
        sc.blit(time_text, (width // 2 - time_text.get_width() // 2, 300))

        btn_width, btn_height = 300, 80
        btn_back = pygame.Rect(width // 2 - btn_width // 2, 420, btn_width, btn_height)
        btn_restart = pygame.Rect(width // 2 - btn_width // 2, 520, btn_width, btn_height)

        pygame.draw.rect(sc, (80, 80, 80), btn_back)
        pygame.draw.rect(sc, (80, 80, 80), btn_restart)

        back_text = font_login.render("Back to Menu", True, (255, 255, 255))
        restart_text = font_login.render("Play Again", True, (255, 255, 255))

        sc.blit(back_text,
                (btn_back.centerx - back_text.get_width() // 2, btn_back.centery - back_text.get_height() // 2))
        sc.blit(restart_text, (btn_restart.centerx - restart_text.get_width() // 2,
                               btn_restart.centery - restart_text.get_height() // 2))

        for event in pg.event.get():
            if event.type == pg.QUIT:
                save_user(user)
                run = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_back.collidepoint(event.pos):
                    button_sound.play()
                    gamemode = "menu"
                    seconds = 0

                elif btn_restart.collidepoint(event.pos):
                    button_sound.play()
                    gamemode = "game"
                    level = user["other_data"]["car_level"]
                    car_img = car_LVL_1 if level == 1 else car_LVL_2 if level == 2 else car_LVL_3
                    player_1_car = car_img
                    player_1_car_rect = car_img.get_rect()
                    player_1_car_rect.left = 50
                    player_1_car_rect.top = 100
                    player_2_car = car_img
                    player_2_car_rect = car_img.get_rect()
                    player_2_car_rect.left = 50
                    player_2_car_rect.top = 450
                    speed_rock = 10.0
                    lives = 3

                    seconds = 0
                    frame_count = 0
                    first_player_direction = "stop"
                    second_player_direction = "stop"
                    rock_rect_1.left = 1200
                    rock_rect_1.top = random.randint(0, 250)
                    rock_rect_2.left = 1900
                    rock_rect_2.top = random.randint(300, 650)
                    diamond_rect.left = 1400
                    game_over_winner = None
                    game_over_seconds = 0


    elif gamemode == "hard" and user is not None:
        main_theme.stop()
        main_theme_2.stop()

        picked_template = random.choice(modifiers)
        current_mod = dict.fromkeys(MODIFIER_KEYS, False)
        for key in picked_template:
            current_mod[key] = True

        if current_mod["start_1hp"]:
            lives = 1
        elif current_mod["not_level"]:
            user['other_data']['car_lvl'] = 1
        elif current_mod["low_diam"]:
            diamond = pg.transform.scale(diamond, (25,50 ))
            rock = pg.transform.scale(diamond, (100, 100))
        elif current_mod["big_car"]:
            if user['other_data']['car_lvl'] == 1:
                car_LVL_1 = pg.transform.scale(car_LVL_1, (225, 104))
            elif user['other_data']['car_lvl'] == 2:
                car_LVL_2 = pg.transform.scale(car_LVL_2, (225, 104))
            else:
                car_LVL_3 = pg.transform.scale(car_LVL_3, (225, 104))
        sc.blit(game_background, (0, 0))
        frame_count += 1
        if frame_count >= 60:
            seconds += 1
            frame_count = 0
            if not current_mod["rocks_acs"]:
                speed_rock += 0.1
            elif current_mod["rocks_acs"]:
                speed_rock += 0.3

        for event in pg.event.get():
            if event.type == pg.QUIT:
                save_user(user)
                run = False

            elif event.type == pg.KEYDOWN:
                inv_move = current_mod["inverted_move"]
                if event.key in (pg.K_w, pg.K_UP):
                    first_player_direction = "down" if inv_move else "up"
                elif event.key in (pg.K_s, pg.K_DOWN):
                    first_player_direction = "up" if inv_move else "down"
                elif event.key in (pg.K_a, pg.K_LEFT):
                    first_player_direction = "right" if inv_move else "left"
                elif event.key in (pg.K_d, pg.K_RIGHT):
                    first_player_direction = "left" if inv_move else "right"

                elif event.key == pg.K_e and lives != 1 and user['other_data']['superpowers']['drugs'] and not current_mod["no_super"]:
                    if user["other_data"]["superpowers"]["drugs"]:
                        if superpowers_parameters["drugs"]["game_limit"] > 0:
                            superpowers_parameters["drugs"]["game_limit"] -= 1
                            seconds += 10
                            lives -= 1
                            drugs_sound.play()
                elif event.key == pg.K_q and user['other_data']['superpowers']['immue'] and not current_mod["no_super"]:
                    if (datetime.now() - immue_last_use_time).total_seconds() >= superpowers_parameters['immue']['cooldown']:
                        immue_sound.play()
                        immue_last_use_time = datetime.now()
                        immue = True
                        if current_car == car_LVL_1:
                            current_car = car_LVL_1_shield
                        elif current_car == car_LVL_2:
                            current_car = car_LVL_2_shield
                        elif current_car == car_LVL_3:
                            current_car = car_LVL_3_shield
                elif event.key == pg.K_r and user['other_data']['superpowers']['rockspeed'] and not current_mod["no_super"]:
                    if superpowers_parameters["rockspeed"]["game_limit"] > 0:
                        superpowers_parameters["rockspeed"]["game_limit"] -= 1
                        speed_rock = 10.0
                        rockspeed_sound.play()
                elif event.key == pg.K_t and user["other_data"]["superpowers"]["hearty_rock"] and not current_mod["no_super"]:
                    if (datetime.now() - hearty_last_use_time).total_seconds() >= 40:
                        hearty_last_use_time = datetime.now()
                        hearty = True
                        rockheart_sound.play()

        if (datetime.now() - immue_last_use_time).total_seconds() >= 10:
            immue = False
            if current_car == car_LVL_1_shield:
                current_car = car_LVL_1
            elif current_car == car_LVL_2_shield:
                current_car = car_LVL_2
            elif current_car == car_LVL_3_shield:
                current_car = car_LVL_3


        level_speed = cars_speed[user["other_data"]["car_level"]]
        if first_player_direction == "up" and current_car_rect.top > 0:
            current_car_rect.top -= level_speed
        elif first_player_direction == "down" and current_car_rect.top < 635:
            current_car_rect.top += level_speed
        elif first_player_direction == "right" and current_car_rect.right < 1200:
            current_car_rect.right += 5
        elif first_player_direction == "left" and current_car_rect.right > 150:
            current_car_rect.right -= 5

        for i in road:
            if i[0] < -150:
                i[0] = width
            i[0] -= 2
            pg.draw.rect(sc, (255, 255, 255), i)

        if rock_rect_1.right > -100:
            sc.blit(rock, rock_rect_1)
            rock_rect_1.right -= speed_rock
        else:
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)

        if rock_rect_2.right > -100:
            sc.blit(rock, rock_rect_2)
            rock_rect_2.right -= speed_rock
        else:
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)

        if diamond_cooldown > 0:
            diamond_cooldown -= 1
        else:
            if diamond_rect.right <= -100:
                if random.random() < 0.004:
                    diamond_rect.left = random.randint(1200, 1600)
                    diamond_rect.top = random.randint(0, 650)
            else:
                sc.blit(diamond, diamond_rect)
                diamond_rect.right -= 25

        sc.blit(current_car, current_car_rect)

        if current_car_rect.colliderect(rock_rect_1) and immue == False and hearty == False and not current_mod["rockhit_2"] and not current_mod["rocks_sec"]:
            lives -= 1
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_1) and immue == False and hearty == False and rockhit_2 == True:
            lives -= 2
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_1) and immue == False and hearty == False and current_mod["rocks_sec"]:
            lives -= 1
            seconds -= 10
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_1) and hearty == True:
            rock_rect_1.left = random.randint(1200, 1600)
            rock_rect_1.top = random.randint(0, 650)
            lives += 1
            hearty = False
            diamond_sound.play()
        if current_car_rect.colliderect(rock_rect_2) and immue == False and hearty == False and not current_mod["rockhit_2"] and not current_mod["rocks_sec"]:
            lives -= 1
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_2) and immue == False and hearty == False and current_mod["rockhit_2"]:
            lives -= 2
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_2) and immue == False and hearty == False and current_mod["rocks_sec"]:
            lives -= 1
            seconds -= 10
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)
            rock_sound.play()
        elif current_car_rect.colliderect(rock_rect_2) and hearty == True:
            rock_rect_2.left = random.randint(1200, 1600)
            rock_rect_2.top = random.randint(0, 650)
            lives += 1
            hearty = False
            diamond_sound.play()
        if current_car_rect.colliderect(diamond_rect) and not current_mod["diamond_no"] and not current_mod["low_diam"]:
            lives += 1
            user["other_data"]["diamonds"] += 2
            diamond_rect.right = -100
            diamond_cooldown = DIAMOND_COOLDOWN_FRAMES
            diamond_sound.play()
        elif current_car_rect.colliderect(diamond_rect) and current_mod["diamond_no"]:
            user["other_data"]["diamonds"] += 2
            diamond_rect.right = -100
            diamond_cooldown = DIAMOND_COOLDOWN_FRAMES
            diamond_sound.play()
        elif current_car_rect.colliderect(diamond_rect) and current_mod["low_diam"]:
            user["other_data"]["diamonds"] += 1
            lives += 2
            diamond_rect.right = -100
            diamond_cooldown = DIAMOND_COOLDOWN_FRAMES
            diamond_sound.play()
        if lives < 1:
            user['other_data']['car_lvl'] = 3
            gameover_sound.play()
            if seconds > user["other_data"]["high_score_seconds"]:
                user["other_data"]["high_score_seconds"] = seconds
            user["other_data"]["matches_count"] += 1
            save_user(user)
            gamemode = "gameover"
            lives = 3

            frame_count = 0
            first_player_direction = "stop"
            current_mus.stop()
            current_theme = random.choice(main_theme_list)
            current_theme.set_volume(0.5)
            current_theme.play(loops=-1)
            superpowers_parameters['drugs']['game_limit'] = 5
            superpowers_parameters['rockspeed']['game_limit'] = 5
        for i in range(lives):
            sc.blit(heart, (i * 60, 10))
        sc.blit(small_diamond, (1050, 600))
        diamond_text = font_login.render(str(user['other_data']['diamonds']), True, (255, 0, 32))
        sc.blit(diamond_text, (1105, 605))
        seconds_text = font_login.render(f"{seconds} sec", True, (255, 0, 32))
        sc.blit(seconds_text, (1050, 640))
        if user['other_data']['superpowers']['drugs']:
            sc.blit(drugs_image, (950, 595))
        if user['other_data']['superpowers']['immue']:
            sc.blit(sheild_image, (850, 595))
        if user['other_data']['superpowers']['rockspeed']:
            sc.blit(timer_image, (850, 645))
        if user['other_data']['superpowers']['hearty_rock']:
            sc.blit(rockheart_image, (950,645))
        label_drugs_use = font_login.render(f"{superpowers_parameters['drugs']['game_limit']}", True,(255, 0, 32))
        label_rockspeed_use = font_login.render(f"{superpowers_parameters['rockspeed']['game_limit']}", True,(255, 0, 32))
        immue_cooldown = int(60 - ((datetime.now() - immue_last_use_time).total_seconds()))
        if immue_cooldown <= 0:
            label_immue_seconds = font_login.render("0", True, (255, 0, 32))
        else:
            label_immue_seconds = font_login.render(f"{immue_cooldown}", True, (255, 0, 32))
        rockheart_cooldown = int(40 - ((datetime.now() - hearty_last_use_time).total_seconds()))
        if rockheart_cooldown <= 0:
            label_rockheart_seconds = font_login.render("0", True, (255, 0, 32))
        else:
            label_rockheart_seconds = font_login.render(f"{rockheart_cooldown}", True, (255, 0, 32))
        if user['other_data']['superpowers']['drugs']:
            sc.blit(label_drugs_use, (1000,595))
        if user['other_data']['superpowers']['rockspeed']:
            sc.blit(label_rockspeed_use, (900, 645))
        if user['other_data']['superpowers']['immue']:
            sc.blit(label_immue_seconds, (900, 595))
        if user['other_data']['superpowers']['hearty_rock']:
            sc.blit(label_rockheart_seconds, (1000, 645))


    elif gamemode == "game2" and user is not None:
        main_theme.stop()
        main_theme_2.stop()
        sc.blit(game_background, (0, 0))
        frame_count += 1
        if frame_count >= 60:
            seconds += 1
            frame_count = 0
            speed_rock += 0.1

        for event in pg.event.get():
            if event.type == pg.QUIT:
                save_user(user)
                run = False

            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_w: first_player_direction = "up"
                elif event.key == pg.K_s: first_player_direction = "down"
                elif event.key == pg.K_a: first_player_direction = "left"
                elif event.key == pg.K_d: first_player_direction = "right"
                elif event.key == pg.K_UP: second_player_direction = "up"
                elif event.key == pg.K_DOWN: second_player_direction = "down"
                elif event.key == pg.K_LEFT: second_player_direction = "left"
                elif event.key == pg.K_RIGHT: second_player_direction = "right"

        level_speed = cars_speed[user["other_data"]["car_level"]]
        if first_player_direction == "up" and player_1_car_rect.top > 0:
            player_1_car_rect.top -= level_speed
        elif first_player_direction == "down" and player_1_car_rect.top < 260:
            player_1_car_rect.top += level_speed
        elif first_player_direction == "right" and player_1_car_rect.right < 1200:
            player_1_car_rect.right += 5
        elif first_player_direction == "left" and player_1_car_rect.right > 150:
            player_1_car_rect.right -= 5

        if second_player_direction == "up" and player_2_car_rect.top > 360:
            player_2_car_rect.top -= level_speed
        elif second_player_direction == "down" and player_2_car_rect.top < 630:
            player_2_car_rect.top += level_speed
        elif second_player_direction == "right" and player_2_car_rect.right < 1200:
            player_2_car_rect.right += 5
        elif second_player_direction == "left" and player_2_car_rect.right > 150:
            player_2_car_rect.right -= 5
        if player_1_car_rect.colliderect(diamond_rect):
            lives += 1
            diamond_rect.right = -100
            diamond_cooldown = DIAMOND_COOLDOWN_FRAMES
        if player_2_car_rect.colliderect(diamond_rect):
            lives2 += 1
            diamond_rect.right = -100
            diamond_cooldown = DIAMOND_COOLDOWN_FRAMES
        for i in road:
            if i[0] < -150:
                i[0] = width
            i[0] -= 2
            pg.draw.rect(sc, (255, 255, 255), i)

        if rock_rect_1.right > -100:
            sc.blit(rock, rock_rect_1)
            rock_rect_1.right -= speed_rock
        else:
            rock_rect_1.left = random.randint(1200, 1400)
            rock_rect_1.top = random.randint(0, 250)

        if rock_rect_2.right > -100:
            sc.blit(rock, rock_rect_2)
            rock_rect_2.right -= speed_rock
        else:
            rock_rect_2.left = random.randint(1200, 1400)
            rock_rect_2.top = random.randint(300, 650)

        if diamond_rect.right <= -100:
            if random.random() < 0.004:
                diamond_rect.left = random.randint(1200, 1600)
                diamond_rect.top = random.randint(0, 650)
        else:
            sc.blit(diamond, diamond_rect)
            diamond_rect.right -= 25

        sc.blit(player_1_car, player_1_car_rect)
        sc.blit(player_2_car, player_2_car_rect)

        if player_1_car_rect.colliderect(rock_rect_1):
            lives -= 1
            rock_rect_1.left = random.randint(1200, 1400)
            rock_rect_1.top = random.randint(0, 250)
        if player_1_car_rect.colliderect(rock_rect_2):
            lives -= 1
            rock_rect_2.left = random.randint(1200, 1400)
            rock_rect_2.top = random.randint(300, 650)

        if player_2_car_rect.colliderect(rock_rect_1):
            lives2 -= 1
            rock_rect_1.left = random.randint(1200, 1400)
            rock_rect_1.top = random.randint(0, 250)
        if player_2_car_rect.colliderect(rock_rect_2):
            lives2 -= 1
            rock_rect_2.left = random.randint(1200, 1400)
            rock_rect_2.top = random.randint(300, 650)

        if lives < 1 or lives2 < 1:
            game_over_seconds = seconds
            if lives < 1 and lives2 >= 1:
                game_over_winner = "P2"
            elif lives2 < 1 and lives >= 1:
                game_over_winner = "P1"
            else:
                game_over_winner = None
            gamemode = "gameover2"
            current_mus.stop()
            current_theme = random.choice(main_theme_list)
            current_theme.set_volume(0.1)
            current_theme.play(loops=-1)
        for i in range(lives):
            sc.blit(heart, (i * 60, 10))
        for i in range(lives2):
            sc.blit(heart, (i * 60, 330))
        seconds_text = font_login.render(f"{seconds} sec", True, (255, 0, 32))
        sc.blit(seconds_text, (1050, 0))

    elif gamemode == "gameover2" and user is not None:
        sc.blit(game_background, (0, 0))

        overlay = pygame.Surface((width, height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        sc.blit(overlay, (0, 0))

        game_over_text = font_login.render("GAME OVER", True, (255, 100, 100))
        sc.blit(game_over_text, (width // 2 - game_over_text.get_width() // 2, 120))

        if game_over_winner == "P1":
            winner_text = font_login.render("PLAYER 1 WINS!", True, (100, 255, 100))
        elif game_over_winner == "P2":
            winner_text = font_login.render("PLAYER 2 WINS!", True, (100, 255, 100))
        else:
            winner_text = font_login.render("DRAW / BOTH LOST", True, (200, 200, 200))

        sc.blit(winner_text, (width // 2 - winner_text.get_width() // 2, 220))

        time_text = font_login.render(f"Survived: {game_over_seconds} seconds", True, (255, 255, 200))
        sc.blit(time_text, (width // 2 - time_text.get_width() // 2, 300))

        btn_width, btn_height = 300, 80
        btn_back = pygame.Rect(width // 2 - btn_width // 2, 420, btn_width, btn_height)
        btn_restart = pygame.Rect(width // 2 - btn_width // 2, 520, btn_width, btn_height)

        pygame.draw.rect(sc, (80, 80, 80), btn_back)
        pygame.draw.rect(sc, (80, 80, 80), btn_restart)

        back_text = font_login.render("Back to Menu", True, (255, 255, 255))
        restart_text = font_login.render("Play Again", True, (255, 255, 255))

        sc.blit(back_text, (btn_back.centerx - back_text.get_width() // 2, btn_back.centery - back_text.get_height() // 2))
        sc.blit(restart_text, (btn_restart.centerx - restart_text.get_width() // 2, btn_restart.centery - restart_text.get_height() // 2))

        for event in pg.event.get():
            if event.type == pg.QUIT:
                save_user(user)
                run = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_back.collidepoint(event.pos):
                    button_sound.play()
                    gamemode = "menu"
                    game_over_winner = None
                    game_over_seconds = 0
                elif btn_restart.collidepoint(event.pos):
                    button_sound.play()
                    gamemode = "game2"
                    level = user["other_data"]["car_level"]
                    car_img = car_LVL_1 if level == 1 else car_LVL_2 if level == 2 else car_LVL_3
                    player_1_car = car_img
                    player_1_car_rect = car_img.get_rect()
                    player_1_car_rect.left = 50
                    player_1_car_rect.top = 100
                    player_2_car = car_img
                    player_2_car_rect = car_img.get_rect()
                    player_2_car_rect.left = 50
                    player_2_car_rect.top = 450
                    speed_rock = 15.0
                    lives = 3
                    lives2 = 3
                    seconds = 0
                    frame_count = 0
                    first_player_direction = "stop"
                    second_player_direction = "stop"
                    rock_rect_1.left = 1200
                    rock_rect_1.top = random.randint(0, 250)
                    rock_rect_2.left = 1900
                    rock_rect_2.top = random.randint(300, 650)
                    diamond_rect.left = 1400
                    game_over_winner = None
                    game_over_seconds = 0

    elif gamemode == "login":
        for i in pg.event.get():
            if i.type == pg.QUIT:
                run = False
            if i.type == pygame.MOUSEBUTTONDOWN and i.button == 1:
                if register_button_rect.collidepoint(i.pos):
                    button_sound.play()
                    if not user_name_text or not password_text:
                        label_empty_fields_bool = True
                        label_invalid_spaces_bool = False
                    elif " " in user_name_text or " " in password_text:
                        label_invalid_spaces_bool = True
                        label_empty_fields_bool = False
                    else:
                        user = register_user(username=user_name_text, password=password_text)
                        if user.get("username"):
                            gamemode = "menu"
                            label_auth_err_bool = False
                            label_register_bool = True
                            label_server_err_bool = False
                            label_empty_fields_bool = False
                            label_invalid_spaces_bool = False
                            user_name_text = ""
                            password_text = ""
                        elif user.get("detail") == "Username already exists":
                            user = auth(username=user_name_text, password=password_text)
                            if user.get("username"):
                                gamemode = "menu"
                                label_auth_err_bool = False
                                label_server_err_bool = False
                                label_empty_fields_bool = False
                                label_invalid_spaces_bool = False
                                user_name_text = ""
                                password_text = ""
                        elif user.get("error") == "connection":
                            label_server_err_bool = True
                            label_empty_fields_bool = False
                            label_invalid_spaces_bool = False
                            user_name_text = ""
                            password_text = ""
                elif sign_in_button.collidepoint(i.pos):
                    button_sound.play()
                    if user_name_text and password_text:
                        label_register_bool = False
                        label_empty_fields_bool = False
                        user = auth(username=user_name_text, password=password_text)
                        if user.get("username"):
                            gamemode = "menu"
                            label_auth_err_bool = False
                            label_server_err_bool = False
                            user_name_text = ""
                            password_text = ""
                        elif user.get("error") == "connection":
                            label_server_err_bool = True
                            user_name_text = ""
                            password_text = ""
                        else:
                            label_auth_err_bool = True
                            user_name_text = ""
                            password_text = ""
                elif user_name_input_box.collidepoint(i.pos):
                    user_name_active = True
                    password_active = False
                elif password_input_box.collidepoint(i.pos):
                    password_active = True
                    user_name_active = False
            elif i.type == pg.KEYDOWN:
                if user_name_active:
                    if i.key == pg.K_RETURN:
                        user_name_text = ''
                    elif i.key == pg.K_BACKSPACE:
                        user_name_text = user_name_text[:-1]
                    elif len(user_name_text) <= 20:
                        user_name_text += i.unicode
                elif password_active:
                    if i.key == pg.K_RETURN:
                        password_text = ''
                    elif i.key == pg.K_BACKSPACE:
                        password_text = password_text[:-1]
                    elif len(password_text) <= 20:
                        password_text += i.unicode

        sc.blit(login_background, (0, 0))
        if label_auth_err_bool:
            sc.blit(label_auth_err, (390, 450))
        if label_register_bool:
            sc.blit(label_register, (390, 450))
        if label_server_err_bool:
            sc.blit(label_server_err, (320, 500))
        if label_empty_fields_bool:
            sc.blit(label_empty_fields, (310, 540))
        if label_invalid_spaces_bool:
            sc.blit(label_invalid_spaces, (310, 515))
        txt_surface1 = font_login.render(user_name_text, True, (0, 0, 0))
        txt_surface2 = font_login.render(password_text, True, (0, 0, 0))
        sc.blit(txt_surface1, (user_name_input_box.x + 5, user_name_input_box.y + 5))
        sc.blit(txt_surface2, (password_input_box.x + 5, password_input_box.y + 5))
        pg.draw.rect(sc, color_active if user_name_active else color_inactive, user_name_input_box, 2)
        pg.draw.rect(sc, color_active if password_active else color_inactive, password_input_box, 2)
        sc.blit(register_button, (400, 400))

    elif gamemode == "settings" and user is not None:
        for i in pg.event.get():
            if i.type == pg.QUIT:
                save_user(user)
                run = False

            if i.type == pygame.MOUSEBUTTONDOWN and i.button == 1:
                if cancel_button_rect.collidepoint(i.pos):
                    label_notenough = ""
                    cancel_btn()
                elif upgrade_button_rect.collidepoint(i.pos):
                    level = user["other_data"]["car_level"]

                    if level < 3:
                        cost = cars_costs[level + 1]
                        if user["other_data"]["diamonds"] >= cost:
                            user["other_data"]["car_level"] += 1
                            user["other_data"]["diamonds"] -= cost
                            save_user(user)
                            label_notenough = ""
                            purchase_sound.play()
                        else:
                            needed = cost - user["other_data"]["diamonds"]
                            label_notenough = font_login.render(f"Not enough diamonds! Need {needed} more.", True, (255, 0, 32))
                elif superpowers_button_rect.collidepoint(i.pos):
                    gamemode = 'superpowers'
                    button_sound.play()
        level = user["other_data"]["car_level"]
        diamonds = user["other_data"]["diamonds"]
        if level < 3:
            next_cost = cars_costs[level + 1]
            needed = max(0, next_cost - diamonds)
            label_car = font_login.render(f"Level {level} | Next: {next_cost} diamonds (need {needed})", True, (255, 0, 32))
        else:
            label_car = font_login.render("Level 3 - MAX LEVEL ACHIEVED!", True, (255, 0, 32))

        sc.blit(settings_background, (0, 0))
        if label_notenough:
            sc.blit(label_notenough, (300, 450))
        sc.blit(upgrade_button, (800, 500))
        sc.blit(label_car, (200, 50))
        sc.blit(cancel_button, (500, 500))
        sc.blit(superpowers_button, (300,500))


        #sc.blit(drugs_button, (200,500))
        #sc.blit(sheild_button, (350, 500))
        #sc.blit(timer_button, (950, 500))
        #sc.blit(rockheart_button, (800, 500))
    elif gamemode == "leader" and user is not None:
        data = {"username": user["username"], "password": user["password"]}
        response = safe_post(db_url_register + 'get_users_by_project', data)
        if response is not None and response.status_code == 200:
            users_records = response.json()
            if "users" in users_records:
                users_records["users"].sort(key=lambda x: x["other_data"]["high_score_seconds"], reverse=True)
            else:
                users_records = {"users": []}
        else:
            users_records = {"users": []}

        sc.blit(menu_background, (0, 0))
        sc.blit(cancel_button, (500, 500))
        title_label = font_login.render("CHAMPIONS:", True, (255, 0, 32))
        sc.blit(title_label, (400, 50))

        now_utc = datetime.now(timezone.utc)
        y_pos = 100
        font_h = font_login.get_height()
        for idx, rec_user in enumerate(users_records["users"][:10], 1):
            other = rec_user["other_data"]
            uname = rec_user["username"]
            level = other.get("car_level", 1)
            score = other["high_score_seconds"]
            matches = other["matches_count"]

            last_raw = other.get("last_login_at")
            if last_raw:
                try:
                    last_dt = datetime.fromisoformat(last_raw)
                    days_ago = (now_utc - last_dt).days
                    if days_ago <= 0:
                        last_seen = "today"
                    elif days_ago == 1:
                        last_seen = "1 day ago"
                    else:
                        last_seen = f"{days_ago} days ago"
                except ValueError:
                    last_seen = "unknown"
            else:
                last_seen = "unknown"

            line1 = font_login.render(f"{idx}. {uname} ({level} lvl)", True, (255, 0, 32))
            line2 = font_login.render(f"{score}s | {matches} matches | {last_seen}", True, (255, 0, 32))
            sc.blit(line1, (100, y_pos))
            sc.blit(line2, (500, y_pos))
            y_pos += font_h + 5
        for i in pg.event.get():
            if i.type == pg.QUIT:
                save_user(user)
                run = False

        if i.type == pygame.MOUSEBUTTONDOWN and i.button == 1:
            if cancel_button_rect.collidepoint(i.pos):
                cancel_btn()
    elif gamemode == "superpowers":
        label_drugs_notenough = font_login.render(f"yo don't have enough diamonds:{user['other_data']['diamonds'] - superpowers_parameters['drugs']['cost']}", True, (255, 255, 255))
        label_immue_notenough = font_login.render(f"yo don't have enough diamonds:{user['other_data']['diamonds'] - superpowers_parameters['immue']['cost']}", True, (255, 255, 255))
        label_timer_notenough = font_login.render(f"yo don't have enough diamonds:{user['other_data']['diamonds'] - superpowers_parameters['rockspeed']['cost']}", True, (255, 255, 255))
        label_heartrock_notenough = font_login.render(f"yo don't have enough diamonds:{user['other_data']['diamonds'] - superpowers_parameters['hearty_rock']['cost']}", True,(255, 255, 255))
        label_already = font_login.render("you already have this power", True,(255, 255, 255))
        sc.blit(super_background, (0,0))
        sc.blit(drugs_button, (200, 500))
        sc.blit(sheild_button, (350, 500))
        sc.blit(timer_button, (950, 500))
        sc.blit(rockheart_button, (800, 500))
        sc.blit(cancel_button, (500, 500))
        sc.blit(label_drugs_cost, (200, 500))
        sc.blit(label_timer_cost, (950, 500))
        sc.blit(label_immue_cost, (350, 500))
        sc.blit(label_heartrock_cost, (800, 500))
        if user['other_data']['superpowers']['drugs']:
            sc.blit(label_drugs_true, (0,100))
        elif user['other_data']['superpowers']['drugs'] == False:
            sc.blit(label_drugs_false, (0, 100))
        if user['other_data']['superpowers']['immue']:
            sc.blit(label_immue_true, (200,100))
        elif user['other_data']['superpowers']['immue'] == False:
            sc.blit(label_immue_false, (200, 100))
        if user['other_data']['superpowers']['rockspeed']:
            sc.blit(label_rockspeed_true, (400,100))
        elif user['other_data']['superpowers']['rockspeed'] == False:
            sc.blit(label_rockspeed_false, (400, 100))
        if user['other_data']['superpowers']['hearty_rock']:
            sc.blit(label_rockheart_true, (700,100))
        elif user['other_data']['superpowers']['hearty_rock'] == False:
            sc.blit(label_rockheart_false, (700, 100))

        if i.type == pygame.MOUSEBUTTONDOWN and i.button == 1:
            if cancel_button_rect.collidepoint(i.pos):
                cancel_btn()
            elif drugs_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] >= superpowers_parameters['drugs']['cost'] and user['other_data']['superpowers']['drugs'] == False:
                purchase_sound.play()
                user['other_data']['diamonds'] -= superpowers_parameters['drugs']['cost']
                user['other_data']['superpowers']['drugs'] = True
            elif drugs_button_rect.collidepoint(i.pos) and user['other_data']['superpowers']['drugs'] == True:
                sc.blit(label_already, (500, 300))
            elif drugs_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] < superpowers_parameters['drugs']['cost']:
                sc.blit(label_drugs_notenough,(500,300))


            elif sheild_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] >= superpowers_parameters['immue']['cost'] and user['other_data']['superpowers']['immue'] == False:
                purchase_sound.play()
                user['other_data']['diamonds'] -= superpowers_parameters['immue']['cost']
                user['other_data']['superpowers']['immue'] = True
            elif sheild_button_rect.collidepoint(i.pos) and user['other_data']['superpowers']['immue'] == True:
                sc.blit(label_already, (500, 300))
            elif sheild_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] < superpowers_parameters['immue']['cost']:
                sc.blit(label_immue_notenough,(500,300))


            elif timer_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] >= superpowers_parameters['rockspeed']['cost'] and user['other_data']['superpowers']['rockspeed'] == False:
                purchase_sound.play()
                user['other_data']['diamonds'] -= superpowers_parameters['rockspeed']['cost']
                user['other_data']['superpowers']['rockspeed'] = True
            elif timer_button_rect.collidepoint(i.pos) and user['other_data']['superpowers']['rockspeed'] == True:
                sc.blit(label_already, (500, 300))
            elif timer_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] < superpowers_parameters['rockspeed']['cost']:
                sc.blit(label_timer_notenough,(500,300))


            elif rockheart_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] > superpowers_parameters['hearty_rock']['cost'] and user['other_data']['superpowers']['hearty_rock'] == False:
                purchase_sound.play()
                user['other_data']['diamonds'] -= superpowers_parameters['hearty_rock']['cost']
                user['other_data']['superpowers']['hearty_rock'] = True
            elif rockheart_button_rect.collidepoint(i.pos) and user['other_data']['superpowers']['hearty_rock'] == True:
                sc.blit(label_already, (500, 300))
            elif rockheart_button_rect.collidepoint(i.pos) and user['other_data']['diamonds'] < superpowers_parameters['rockspeed']['cost']:
                sc.blit(label_heartrock_notenough, (50, 500))

        elif i.type == pygame.MOUSEBUTTONDOWN and i.button == 3:
            if drugs_button_rect.collidepoint(i.pos):
                sc.blit(label_drugs_how, (0, 0))
            elif sheild_button_rect.collidepoint(i.pos):
                sc.blit(label_immue_how, (0, 0))
            elif timer_button_rect.collidepoint(i.pos):
                sc.blit(label_rockspeed_how, (0, 0))
            elif rockheart_button_rect.collidepoint(i.pos):
                sc.blit(label_rockheart_how, (0, 0))
        for i in pg.event.get():
            if i.type == pg.QUIT:
                save_user(user)
                run = False

    pg.display.update()
    clock.tick(fps)
    prev_gamemode = gamemode

pg.quit()