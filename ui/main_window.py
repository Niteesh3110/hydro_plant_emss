# game/pixel_resort.py

import random
import pygame
from pygame.locals import QUIT, KEYDOWN, K_ESCAPE, K_1, K_2, K_3

from domain.simulation import EMSSSimulator, SimulationConfig


WIDTH, HEIGHT = 960, 540
FPS = 60
SIM_STEP_MS = 200  # simulation step every 200 ms


class Room:
    def __init__(self, rect: pygame.Rect, room_type: str):
        self.rect = rect
        self.room_type = room_type  # "standard" or "suite"
        self.occupied = False


class CustomerSprite(pygame.sprite.Sprite):
    def __init__(self, area_rect: pygame.Rect):
        super().__init__()
        self.image = pygame.Surface((10, 10))
        self.image.fill((255, 255, 255))
        self.rect = self.image.get_rect()
        self.area_rect = area_rect
        self.speed = 1.0
        self.pick_new_target()
        # start at a random position in the area
        self.rect.center = (
            self.area_rect.left + self.area_rect.width * random.random(),
            self.area_rect.top + self.area_rect.height * random.random(),
        )

    def pick_new_target(self):
        self.target_x = (
            self.area_rect.left
            + self.area_rect.width * 0.1
            + self.area_rect.width * 0.8 * random.random()
        )
        self.target_y = (
            self.area_rect.top
            + self.area_rect.height * 0.1
            + self.area_rect.height * 0.8 * random.random()
        )

    def update(self):
        dx = self.target_x - self.rect.centerx
        dy = self.target_y - self.rect.centery
        dist2 = dx * dx + dy * dy
        if dist2 < 4:
            self.pick_new_target()
            return
        dist = dist2 ** 0.5
        vx = self.speed * dx / dist
        vy = self.speed * dy / dist
        self.rect.centerx += vx
        self.rect.centery += vy


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("EMSS Resort Pixel Simulation")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)

    # --- EMSS simulator with more stressful config so battery/generator/unserved show up ---
    config = SimulationConfig(
        max_turbine_kw=200.0,          # weaker hydro
        max_reservoir_m3=100_000.0,
        min_reservoir_m3=5_000.0,
        base_inflow_m3_per_hour=120.0,
        battery_capacity_kwh=200.0,    # smaller battery
        max_charge_kw=80.0,
        max_discharge_kw=80.0,
        round_trip_efficiency=0.9,
        max_generator_kw=150.0,        # limited generator
        fuel_cost_per_kwh=0.2,
        num_standard_rooms=20,
        num_suite_rooms=5,
        standard_room_kw_per_room=3.0,
        suite_room_kw_per_room=5.0,
        restaurant_base_kw=25.0,
        restaurant_kw_per_customer=0.7,
        spa_base_kw=12.0,
        spa_kw_per_customer=0.9,
        lobby_base_kw=10.0,
        lobby_kw_per_customer=0.3,
    )
    sim = EMSSSimulator(config)
    record = sim.step_once()

    # --- Layout: resort & hydro ---

    # Resort block on right
    resort_w, resort_h = 360, 280
    resort_x = WIDTH - resort_w - 40
    resort_y = (HEIGHT - resort_h) // 2
    resort_rect = pygame.Rect(resort_x, resort_y, resort_w, resort_h)

    # Rooms area (top 60%)
    rooms_h = int(resort_h * 0.6)
    rooms_rect = pygame.Rect(resort_x, resort_y, resort_w, rooms_h)

    # Shared areas (bottom 40%)
    shared_h = resort_h - rooms_h
    shared_y = resort_y + rooms_h
    third_w = resort_w // 3

    restaurant_rect = pygame.Rect(resort_x, shared_y, third_w, shared_h)
    spa_rect = pygame.Rect(resort_x + third_w, shared_y, third_w, shared_h)
    lobby_rect = pygame.Rect(resort_x + 2 * third_w, shared_y, third_w, shared_h)

    # Hydro plant block on left
    hydro_rect = pygame.Rect(60, HEIGHT // 2 - 40, 60, 80)

    # --- Build room grid inside rooms_rect ---

    room_cols = 5
    room_rows = 5
    tile_w = rooms_rect.width // room_cols
    tile_h = rooms_rect.height // room_rows

    rooms: list[Room] = []

    # bottom row = suites, others = standard
    for row in range(room_rows):
        for col in range(room_cols):
            x = rooms_rect.left + col * tile_w
            y = rooms_rect.top + row * tile_h
            rect = pygame.Rect(x + 1, y + 1, tile_w - 2, tile_h - 2)  # small gap

            if row == room_rows - 1:
                room_type = "suite"
            else:
                room_type = "standard"

            rooms.append(Room(rect, room_type))

    # --- Customers in shared areas ---

    customers_by_area = {
        "restaurant": pygame.sprite.Group(),
        "spa": pygame.sprite.Group(),
        "lobby": pygame.sprite.Group(),
    }

    def sync_customers(area_name: str, logical_count: int, area_rect: pygame.Rect):
        group = customers_by_area[area_name]
        # cap the number of sprites; we don't want 100 on screen
        desired = min(15, max(0, logical_count // 2))

        # Add sprites if too few
        while len(group) < desired:
            c = CustomerSprite(area_rect)
            group.add(c)

        # Remove extras if too many
        while len(group) > desired:
            sprite = group.sprites()[-1]
            group.remove(sprite)

    # --- History for telemetry view ---

    history: list[dict] = []
    max_history = 60

    # --- View state (tabs) ---

    current_view = "world"  # "world", "telemetry", "bars"

    last_sim_tick = pygame.time.get_ticks()
    running = True

    # ---- Drawing helpers ----

    def draw_tabs_header():
        """Draw simple tab labels on top."""
        bar_rect = pygame.Rect(0, 0, WIDTH, 30)
        pygame.draw.rect(screen, (30, 30, 30), bar_rect)
        labels = [("1 World", "world"), ("2 Telemetry", "telemetry"), ("3 Bars", "bars")]
        x = 20
        for text, view_name in labels:
            color = (255, 255, 0) if current_view == view_name else (200, 200, 200)
            surf = font.render(text, True, color)
            screen.blit(surf, (x, 6))
            x += surf.get_width() + 20

    def draw_world_view():
        screen.fill((20, 40, 20))

        # Hydro plant
        pygame.draw.rect(screen, (50, 150, 255), hydro_rect)

        # Resort mood based on generator/unserved
        generator = record["generator_kw"]
        unserved = record["unserved_kw"]
        if unserved > 0:
            resort_color = (255, 80, 80)
        elif generator > 0:
            resort_color = (255, 210, 100)
        else:
            resort_color = (100, 220, 140)
        pygame.draw.rect(screen, resort_color, resort_rect, border_radius=6)
        pygame.draw.rect(screen, (30, 30, 30), resort_rect, 2, border_radius=6)

        # Rooms grid
        for room in rooms:
            if room.room_type == "standard":
                base_color = (70, 120, 70)
            else:  # suite
                base_color = (90, 90, 140)

            color = base_color
            if room.occupied:
                color = (
                    min(255, color[0] + 40),
                    min(255, color[1] + 40),
                    min(255, color[2] + 40),
                )
            pygame.draw.rect(screen, color, room.rect)
            pygame.draw.rect(screen, (20, 20, 20), room.rect, 1)

        # Shared areas
        pygame.draw.rect(screen, (110, 70, 50), restaurant_rect)
        pygame.draw.rect(screen, (70, 70, 110), spa_rect)
        pygame.draw.rect(screen, (120, 120, 60), lobby_rect)

        # Customers
        for group in customers_by_area.values():
            group.draw(screen)

        # HUD
        resort_state = record["resort"]
        lines = [
            f"Time: {record['time'].strftime('%H:%M')}",
            f"Demand: {record['demand_kw']:.1f} kW",
            f"Hydro: {record['hydro_kw']:.1f} kW",
            f"Battery: {record['battery_kw']:.1f} kW",
            f"Generator: {record['generator_kw']:.1f} kW",
            f"Unserved: {record['unserved_kw']:.1f} kW",
            f"Guests: {resort_state['total_guests']}",
            f"Rooms occ: {resort_state['standard_rooms_occupied'] + resort_state['suite_rooms_occupied']}",
        ]
        y = 40
        for line in lines:
            surf = font.render(line, True, (230, 230, 230))
            screen.blit(surf, (20, y))
            y += 20

    def draw_telemetry_view():
        screen.fill((10, 10, 30))

        title = font.render("Telemetry (most recent at bottom)", True, (255, 255, 255))
        screen.blit(title, (20, 40))

        # Show last N records
        y = 70
        # show newest last (scrolling feeling)
        for rec in history[-max_history:]:
            s = (
                f"{rec['time'].strftime('%H:%M')}  "
                f"D:{rec['demand_kw']:.0f}  "
                f"H:{rec['hydro_kw']:.0f}  "
                f"B:{rec['battery_kw']:.0f}  "
                f"G:{rec['generator_kw']:.0f}  "
                f"U:{rec['unserved_kw']:.0f}"
            )
            surf = font.render(s, True, (200, 200, 220))
            screen.blit(surf, (20, y))
            y += 18
            if y > HEIGHT - 20:
                break

    def draw_bars_view():
        screen.fill((0, 0, 0))

        title = font.render("Power Split (current step)", True, (255, 255, 255))
        screen.blit(title, (20, 40))

        labels = ["Demand", "Hydro", "Battery", "Generator", "Unserved"]
        raw_values = [
            record["demand_kw"],
            record["hydro_kw"],
            record["battery_kw"],
            record["generator_kw"],
            record["unserved_kw"],
        ]

        # Use absolute values for bar height (battery can be negative when charging)
        values = [abs(v) for v in raw_values]
        max_val = max(1.0, max(values))
        bar_width = 80
        gap = 30
        base_x = 60
        base_y = HEIGHT - 80
        scale = (HEIGHT - 180) / max_val

        for i, (label, val, raw_val) in enumerate(zip(labels, values, raw_values)):
            x = base_x + i * (bar_width + gap)
            h = int(val * scale)
            if label == "Unserved":
                color = (200, 40, 40)
            elif label == "Battery":
                color = (80, 80, 200)
            elif label == "Generator":
                color = (200, 160, 80)
            else:
                color = (80, 180, 80)

            rect = pygame.Rect(x, base_y - h, bar_width, h)
            pygame.draw.rect(screen, color, rect)
            lab_surf = font.render(label, True, (220, 220, 220))
            screen.blit(lab_surf, (x, base_y + 5))
            val_surf = font.render(f"{raw_val:.0f}", True, (200, 200, 200))
            screen.blit(val_surf, (x, base_y - h - 20))

    # --- Main loop ---

    while running:
        dt = clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
                elif event.key == K_1:
                    current_view = "world"
                elif event.key == K_2:
                    current_view = "telemetry"
                elif event.key == K_3:
                    current_view = "bars"

        # Advance EMSS periodically
        now = pygame.time.get_ticks()
        if now - last_sim_tick >= SIM_STEP_MS:
            last_sim_tick = now
            record = sim.step_once()
            resort_state = record["resort"]

            # keep history for telemetry view
            history.append(record)
            if len(history) > max_history:
                history.pop(0)

            # map resort occupancy to room tiles
            std_occ = resort_state["standard_rooms_occupied"]
            suite_occ = resort_state["suite_rooms_occupied"]

            # reset
            for room in rooms:
                room.occupied = False

            std_rooms = [r for r in rooms if r.room_type == "standard"]
            suite_rooms = [r for r in rooms if r.room_type == "suite"]

            for r in std_rooms[:std_occ]:
                r.occupied = True
            for r in suite_rooms[:suite_occ]:
                r.occupied = True

            # sync customers in shared areas
            sync_customers("restaurant", resort_state["restaurant_customers"], restaurant_rect)
            sync_customers("spa", resort_state["spa_customers"], spa_rect)
            sync_customers("lobby", resort_state["lobby_customers"], lobby_rect)

        # Update customers every frame
        for group in customers_by_area.values():
            group.update()

        # Draw current view
        if current_view == "world":
            draw_world_view()
        elif current_view == "telemetry":
            draw_telemetry_view()
        elif current_view == "bars":
            draw_bars_view()

        # Tabs header on top (overlay)
        draw_tabs_header()

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
