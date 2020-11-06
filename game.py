#!/usr/bin/env python
from __future__ import annotations

import arcade

from typing import (
    List, Dict, Any, Optional, Union
)
from arcade import (
    draw_line, draw_circle_outline, draw_rectangle_filled, create_line,
    draw_rectangle_outline, draw_text, SpriteList, ShapeElementList, Sprite
)
from arcade.arcade_types import Color

from scheduling import EventsCreator, ScheduledEvent, EventsScheduler
from observers import ObjectsOwner, OwnedObject
from data_containers import DividedSpriteList
from views import WindowView, LoadingScreen
from user_interface import UiSpriteList
from utils.functions import (
    timer, get_screen_size, get_path_to_file, log, to_rgba
)
from user_interface import (
    Button, CheckButton, TextInputField
)
from colors import MAP_GREEN, RED, BROWN, BLACK, WHITE
from menu import Menu, SubMenu

SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_size()
SCREEN_X, SCREEN_Y = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
SCREEN_CENTER = SCREEN_X, SCREEN_Y
UPDATE_RATE = 1 / 30
PROFILING_LEVEL = 0  # higher the level, more functions will be time-profiled
DEBUG = True


def spawn_test_unit(position, unit_name: str, player: Player) -> Unit:
    unit_name = get_path_to_file(unit_name)
    return Unit(unit_name, player, UnitWeight.LIGHT, position)


class Window(arcade.Window, EventsCreator):

    def __init__(self, width: int, height: int, update_rate: float):
        arcade.Window.__init__(self, width, height, update_rate=update_rate)
        self.center_window()
        self.events_scheduler = EventsScheduler(update_rate=update_rate)

        self._updated: List = []
        self.drawn: List = []

        self.menu_view = Menu()
        self.game_view: Optional[Game] = None

        self.create_submenus()

        self.show_view(LoadingScreen(loaded_view=self.menu_view))

        # cursor-related:
        # store viewport data to avoid redundant get_viewport() calls and call
        # get_viewport only when viewport is actually changed:
        self.current_viewport = self.get_viewport()
        self.cursor = MouseCursor(self, get_path_to_file('normal.png'))

        # keyboard-related:
        self.keyboard = KeyboardHandler(window=self)

    @property
    def updated(self):
        return self._updated

    @updated.setter
    def updated(self, value: List[SpriteList]):
        self._updated = value
        try:
            self.cursor.updated_spritelists = value
        except AttributeError:
            pass  # MouseCursor is not initialised yet

    def create_submenus(self):
        sound_submenu = SubMenu('Sound', background_color=RED)
        graphics_submenu = SubMenu('Graphics', background_color=BROWN)
        game_settings = SubMenu('Game settings', background_color=BLACK)

        ui_element_texture = get_path_to_file('small_button_none.png')
        sound_ui_elements = [
            Button(ui_element_texture),
            CheckButton(ui_element_texture),
            TextInputField(ui_element_texture)
        ]
        for element in sound_ui_elements:
            element.register_to_objectsowners()
        sound_submenu.set_updated_and_drawn_lists()

    def create_new_game(self):
        self.game_view = Game()

    def start_new_game(self):
        if self.game_view is not None:
            self.show_view(self.game_view)

    def on_update(self, delta_time: float):
        self.current_view.on_update(delta_time)
        if (cursor := self.cursor).active:
            cursor.update()
        self.events_scheduler.update()

    def on_draw(self):
        self.clear()
        self.current_view.on_draw()
        if (cursor := self.cursor).visible:
            cursor.draw()

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        if self.cursor.active:
            if self.current_view is self.game_view:
                left, _, bottom, _ = self.current_viewport
                self.cursor.on_mouse_motion(x + left, y + bottom, dx, dy)
            else:
                self.cursor.on_mouse_motion(x, y, dx, dy)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        if self.cursor.active:
            self.cursor.on_mouse_press(x, y, button, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int,
                         modifiers: int):
        if self.cursor.active:
            self.cursor.on_mouse_release(x, y, button, modifiers)

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      buttons: int, modifiers: int):
        if self.cursor.active:
            left, _, bottom, _ = self.current_viewport
            self.cursor.on_mouse_drag(x + left, y + bottom, dx, dy, buttons, modifiers)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        if self.cursor.active:
            self.cursor.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_key_press(self, symbol: int, modifiers: int):
        if self.keyboard.active:
            self.keyboard.on_key_press(symbol, modifiers)

    def on_key_release(self, symbol: int, modifiers: int):
        self.keyboard.on_key_release(symbol, modifiers)

    def show_view(self, new_view: WindowView):
        if new_view.requires_loading:
            self.show_view(LoadingScreen(loaded_view=new_view))
        else:
            super().show_view(new_view)

    def toggle_view(self):
        # debug method to be replaced with callbacks of UiElements
        if self.current_view is self.menu_view:
            self.create_new_game()
            self.start_new_game()
            # self.menu_view.toggle_submenu(self.sound_submenu)
        else:
            self.show_view(self.menu_view)

    def toggle_mouse_and_keyboard(self, value: bool, only_mouse=False):
        try:
            self.cursor.active = value
            self.cursor.visible = value
            if not only_mouse:
                self.keyboard.active = value
        except AttributeError:
            pass

    def save_game(self):
        # TODO: save GameObject.total_objects_count (?)
        raise NotImplementedError

    def load_game(self):
        raise NotImplementedError

    def close(self):
        log(f'Terminating application...', 1)
        super().close()


class Game(WindowView, EventsCreator, ObjectsOwner):
    instance: Optional[Game] = None

    def __init__(self, debug: bool = DEBUG):
        WindowView.__init__(self, requires_loading=True)
        EventsCreator.__init__(self)
        self.assign_reference_to_self_for_all_classes()

        self.paused = False

        # SpriteLists:
        self.terrain_objects = SpriteList(is_static=True)
        self.vehicles_threads = SpriteList(is_static=True)
        self.buildings = DividedSpriteList(is_static=True)
        self.units = DividedSpriteList()
        self.selection_markers_sprites = UiSpriteList()
        self.interface = UiSpriteList()

        self.fog_of_war = FogOfWar()
        self.map = Map(20 * 100, 20 * 100, 20, 20)

        self.set_updated_and_drawn_lists()

        # Settings, game-progress data, etc.
        self.player_configs: Dict[str, Any] = self.load_player_configs()

        # Units belongs to the Players, Players belongs to the Factions, which
        # are updated each frame to evaluate AI, enemies-visibility, etc.
        self.factions: Dict[int, Faction] = {}
        self.players: Dict[int, Player] = {}

        self.local_human_player: Optional[Player] = None

        self.missions: Dict[int, Mission] = {}
        self.current_mission: Optional[Mission] = None

        self.debug = DEBUG
        if DEBUG:
            self.debugged = []
            self.map_grid = self.create_map_debug_grid()

        self.test_methods()

    def assign_reference_to_self_for_all_classes(self):
        name = self.__class__.__name__.lower()
        for _class in (c for c in globals().values() if hasattr(c, name)):
            setattr(_class, name, self)
        Game.instance = self.window.cursor.game = self

    def on_show_view(self):
        super().on_show_view()
        self.window.toggle_mouse_and_keyboard(True)

    def test_methods(self):
        self.test_scheduling_events()
        self.test_factions_and_players_creation()
        self.test_units_spawning()
        self.test_buildings_spawning()

    def test_scheduling_events(self):
        event = ScheduledEvent(self, 2, self.scheduling_test, repeat=True)
        self.schedule_event(event)

    def test_factions_and_players_creation(self):
        faction = Faction(name='Freemen')
        player = Player(id=2, faction=faction, cpu=False)
        cpu_player = CpuPlayer()
        self.local_human_player: Optional[Player] = self.players[2]
        player.start_war_with(cpu_player)
        # self.factions[2].start_war_with(self.factions[4])

    def test_units_spawning(self):
        player_units = self.spawn_local_human_player_units()
        cpu_units = self.spawn_cpu_units()
        self.units.extend(player_units + cpu_units)

    def spawn_local_human_player_units(self) -> List[Unit]:
        spawned_units = []
        player = self.players[2]
        name = 'jeep_blue.png'
        # spawned_units.append(spawn_test_unit((100, 100), name, player=player))
        for x in range(30, SCREEN_WIDTH, TILE_WIDTH * 4):
            for y in range(30, SCREEN_HEIGHT, TILE_HEIGHT * 4):
                spawned_units.append(spawn_test_unit((x, y), name, player=player))
        return spawned_units

    def spawn_cpu_units(self) -> List[Unit]:
        spawned_units = []
        position = 600, 600
        name = "medic_truck_red.png"
        cpu_unit = spawn_test_unit(position, name, player=self.players[4])
        spawned_units.append(cpu_unit)
        return spawned_units

    def test_buildings_spawning(self):
        building = Building(
            get_path_to_file('small_button_none.png'),
            self.players[4],
            (400, 600),
            produces=Unit
        )
        self.buildings.append(building)

    def load_player_configs(self) -> Dict[str, Any]:
        configs: Dict[str, Any] = {}
        # TODO
        return configs

    @staticmethod
    def next_free_player_color() -> Color:
        return 0, 0, 0

    def register(self, acquired: OwnedObject):
        acquired: Union[Player, Faction, PlayerEntity]
        if isinstance(acquired, (Unit, Building)):
            self.register_player_entity(acquired)
        else:
            self.register_player_or_faction(acquired)

    def register_player_entity(self, registered: Union[Unit, Building]):
        if not registered.is_building:
            self.units.append(registered)
        else:
            self.buildings.append(registered)

    def register_player_or_faction(self, registered: Union[Player, Faction]):
        if isinstance(registered, Player):
            self.players[registered.id] = registered
        else:
            self.factions[registered.id] = registered

    def unregister(self, owned: OwnedObject):
        owned: Union[PlayerEntity, Player, Faction]
        if isinstance(owned, PlayerEntity):
            self.unregister_player_entity(owned)
        else:
            self.unregister_player_or_faction(owned)

    def unregister_player_entity(self, owned: Union[PlayerEntity]):
        owned: Union[Unit, Building]
        if not owned.is_building:
            self.units.remove(owned)
        else:
            self.buildings.remove(owned)

    def unregister_player_or_faction(self, owned: Union[Player, Faction]):
        if isinstance(owned, Player):
            del self.players[owned.id]
        else:
            del self.factions[owned.id]

    def get_notified(self, *args, **kwargs):
        pass

    @timer(level=1, global_profiling_level=PROFILING_LEVEL)
    def on_update(self, delta_time: float):
        if not self.paused:
            super().on_update(delta_time)
            self.update_factions_and_players()

    def update_factions_and_players(self):
        for faction in self.factions.values():
            faction.update()

    @timer(level=1, global_profiling_level=PROFILING_LEVEL)
    def on_draw(self):
        super().on_draw()
        if self.debug:
            self.draw_debugging()
        if self.paused:
            self.draw_paused_dialog()

    @timer(level=3, global_profiling_level=PROFILING_LEVEL)
    def draw_debugging(self):
        if self.map_grid is None:
            self.map_grid = self.create_map_debug_grid()
        self.draw_debugged_map_grid()
        self.draw_debugged_mouse_pointed_nodes()
        self.draw_debugged()

    def draw_debugged_map_grid(self):
        self.map_grid.draw()

    def draw_debugged_mouse_pointed_nodes(self):
        position = self.map.normalize_position(*self.window.cursor.position)
        node = self.map.position_to_node(*position)

        draw_circle_outline(node.x, node.y, 10, RED, 2)

        for adj in node.adjacent_nodes + [node]:
            color = to_rgba(WHITE, 25) if adj.walkable else to_rgba(RED, 25)
            draw_rectangle_filled(adj.x, adj.y, TILE_WIDTH,
                                         TILE_HEIGHT, color)
            draw_circle_outline(*adj.position, 5, WHITE, 1)

    def draw_debugged(self):
        self.draw_debug_paths()
        self.draw_debug_lines_of_sight()

    def draw_debug_paths(self):
        for path in (u.path for u in self.local_human_player.units if u.path):
            for i, point in enumerate(path):
                try:
                    end = path[i + 1]
                    draw_line(*point, *end, MAP_GREEN, 2)
                except IndexError:
                    pass

    def draw_debug_lines_of_sight(self):
        for unit in (u for u in self.local_human_player.units if u.known_enemies):
            for enemy in unit.known_enemies:
                draw_line(*unit.position, *enemy.position, RED)

    def draw_paused_dialog(self):
        draw_rectangle_filled(*SCREEN_CENTER, SCREEN_WIDTH, 200, to_rgba(BLACK, 150))
        draw_text('GAME PAUSED', SCREEN_X, SCREEN_Y, WHITE, 30,
                  anchor_x='center', anchor_y='center')

    def toggle_pause(self):
        self.paused = paused = not self.paused
        self.window.toggle_mouse_and_keyboard(not paused, only_mouse=True)

    def create_map_debug_grid(self) -> arcade.ShapeElementList:
        grid = arcade.ShapeElementList()
        # horizontal lines:
        for i in range(self.map.rows):
            y = i * TILE_HEIGHT
            h_line = create_line(0, y, SCREEN_WIDTH, y, BLACK, 1)
            grid.append(h_line)

            y = i * TILE_HEIGHT + TILE_HEIGHT // 2
            h2_line = create_line(TILE_WIDTH // 2, y, SCREEN_WIDTH, y, WHITE, 1)
            grid.append(h2_line)
        # vertical lines:
        for j in range(self.map.columns):
            x = j * TILE_WIDTH
            v_line = create_line(x, 0, x, SCREEN_HEIGHT, BLACK, 1)
            grid.append(v_line)

            x = j * TILE_WIDTH + TILE_WIDTH // 2
            v2_line = create_line(x, TILE_HEIGHT // 2, x, SCREEN_HEIGHT, WHITE, 1)
            grid.append(v2_line)
        return grid


if __name__ == '__main__':
    # these imports are placed here to avoid circular-imports issue:
    from map import TILE_WIDTH, TILE_HEIGHT, PATH, Map, GridPosition
    from player import Faction, Player, CpuPlayer, PlayerEntity
    from keyboard_handling import KeyboardHandler
    from mouse_handling import MouseCursor
    from units import Unit, UnitWeight
    from fog_of_war import FogOfWar
    from buildings import Building
    from missions import Mission

    window = Window(SCREEN_WIDTH, SCREEN_HEIGHT, UPDATE_RATE)
    arcade.run()
