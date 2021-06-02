#!/usr/bin/env python
from __future__ import annotations

__title__ = 'RaTS: Real (almost) Time Strategy'
__author__ = 'Rafał "Akapkotel" Trąbski'
__license__ = "Share Alike Attribution-NonCommercial-ShareAlike 4.0"
__version__ = "0.0.3"
__maintainer__ = "Rafał Trąbski"
__email__ = "rafal.trabski@mises.pl"
__status__ = "development"
__credits__ = []

import random

from typing import (Any, Dict, List, Optional, Set, Union, Generator)

import arcade
from functools import partial
from dataclasses import dataclass
from arcade import (
    SpriteList, create_line, draw_circle_outline, draw_line,
    draw_rectangle_filled, draw_text
)
from arcade.arcade_types import Color, Point

from effects.sound import AudioPlayer
from persistency.configs_handling import read_csv_files
from user_interface.user_interface import (
    Frame, Button, UiBundlesHandler, UiElementsBundle, UiSpriteList,
    ScrollableContainer
)
from utils.colors import BLACK, GREEN, RED, WHITE
from utils.data_types import Viewport
from utils.functions import (
    clamp, get_path_to_file, get_screen_size, log, timer, to_rgba,
    average_position_of_points_group, SEPARATOR
)
from utils.improved_spritelists import (
    SelectiveSpriteList, SpriteListWithSwitch
)
from utils.ownership_relations import OwnedObject
from utils.scheduling import EventsCreator, EventsScheduler, ScheduledEvent
from utils.views import LoadingScreen, LoadableWindowView, Updateable

# CIRCULAR IMPORTS MOVED TO THE BOTTOM OF FILE!
BASIC_UI = 'basic_ui'
EDITOR = 'editor'
BUILDINGS_PANEL = 'building_panel'
UNITS_PANEL = 'units_panel'

FULL_SCREEN = False
SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_size()
SCREEN_X, SCREEN_Y = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
SCREEN_CENTER = SCREEN_X, SCREEN_Y
MINIMAP_WIDTH = 388
MINIMAP_HEIGHT = 196

TILE_WIDTH = 60
TILE_HEIGHT = 40
SECTOR_SIZE = 8
ROWS = 100
COLUMNS = 150

GAME_SPEED = 1.0

UPDATE_RATE = 1 / (30 * GAME_SPEED)
PROFILING_LEVEL = 0  # higher the level, more functions will be time-profiled
PYPROFILER = False
DEBUG = False


@dataclass
class Settings:
    """
    Just a simple data container for convenient storage and acces to bunch of
    minor variables, which would overcrowd Window __init__.
    """
    debug: bool
    vehicles_threads: bool
    threads_fadeout: int
    shot_blasts: bool


class Window(arcade.Window, EventsCreator):

    def __init__(self, width: int, height: int, update_rate: float):
        arcade.Window.__init__(self, width, height, update_rate=update_rate)
        self.set_fullscreen(FULL_SCREEN)
        self.set_caption(__title__)

        self.settings = Settings(False, True, 2, True)  # shared with Game

        self.events_scheduler = EventsScheduler(update_rate=update_rate)

        self.sound_player = AudioPlayer()

        self.save_manger = SaveManager('saved_games', 'scenarios')

        self._updated: List[Updateable] = []

        # Settings, gameobjects configs, game-progress data, etc.
        self.configs = read_csv_files('resources/configs')

        # views:
        self.menu_view = Menu()
        self.game_view: Optional[Game] = None
        # self.menu_view.create_submenus()

        self.show_view(LoadingScreen(loaded_view=self.menu_view))

        # cursor-related:
        self.cursor = MouseCursor(self, get_path_to_file('normal.png'))
        # store viewport data to avoid redundant get_viewport() calls and call
        # get_viewport only when viewport is actually changed:
        self.current_viewport = self.get_viewport()

        # keyboard-related:
        self.keyboard = KeyboardHandler(window=self)

    @property
    def screen_center(self) -> Point:
        left, _, bottom, _ = self.current_view.viewport
        return left + SCREEN_X, bottom + SCREEN_Y

    @property
    def updated(self) -> List[Updateable]:
        return self._updated

    @updated.setter
    def updated(self, value: List[Updateable]):
        self._updated = value
        try:
            self.cursor.updated_spritelists = value
        except AttributeError:
            pass  # MouseCursor is not initialised yet

    def toggle_fullscreen(self):
        self.set_fullscreen(not self.fullscreen)
        if not self.fullscreen:
            self.set_size(SCREEN_WIDTH - 1, SCREEN_HEIGHT - 1)
            self.center_window()

    @property
    def is_game_running(self) -> bool:
        return self.game_view is not None and self.current_view == self.game_view

    def start_new_game(self):
        if self.game_view is None:
            self.game_view = Game()
        self.show_view(self.game_view)

    def quit_current_game(self):
        self.game_view = None
        self.show_view(self.menu_view)
        self.menu_view.toggle_game_related_buttons()

    @timer(level=1, global_profiling_level=PROFILING_LEVEL)
    def on_update(self, delta_time: float):
        log(f'Time: {delta_time}{SEPARATOR}', console=False)
        self.current_view.on_update(delta_time)
        if (cursor := self.cursor).active:
            cursor.update()
        self.events_scheduler.update()
        self.sound_player.on_update()
        super().on_update(delta_time)

    def on_draw(self):
        self.clear()
        self.current_view.on_draw()
        if (cursor := self.cursor).visible:
            cursor.draw()

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        if self.cursor.active:
            if self.current_view is self.game_view:
                left, _, bottom, _ = self.current_view.viewport
                self.cursor.on_mouse_motion(x + left, y + bottom, dx, dy)
            else:
                self.cursor.on_mouse_motion(x, y, dx, dy)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        if self.cursor.active:
            self.cursor.on_mouse_press(x, y, button, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int,
                         modifiers: int):
        if self.cursor.active:
            left, _, bottom, _ = self.current_view.viewport
            self.cursor.on_mouse_release(x + left, y + bottom, button, modifiers)

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float,
                      buttons: int, modifiers: int):
        if self.cursor.active:
            left, _, bottom, _ = self.current_view.viewport
            self.cursor.on_mouse_drag(x + left, y + bottom, dx, dy, buttons, modifiers)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        if self.cursor.active:
            self.cursor.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_key_press(self, symbol: int, modifiers: int):
        if self.keyboard.active:
            self.keyboard.on_key_press(symbol, modifiers)

    def on_key_release(self, symbol: int, modifiers: int):
        self.keyboard.on_key_release(symbol, modifiers)

    def show_view(self, new_view: LoadableWindowView):
        if new_view.requires_loading:
            self.show_view(LoadingScreen(loaded_view=new_view))
        else:
            super().show_view(new_view)

    def toggle_mouse_and_keyboard(self, value: bool, only_mouse=False):
        try:
            self.cursor.active = value
            self.cursor.visible = value
            if not only_mouse:
                self.keyboard.active = value
        except AttributeError:
            pass

    def change_viewport(self, dx: float, dy: float):
        """
        Change displayed area accordingly to the current position of player
        in the game world. If not in game, return static menu viewport.
        """
        game_map = self.game_view.map
        left, right, bottom, top = self.get_viewport()
        new_left = clamp(left - dx, game_map.width - SCREEN_WIDTH, 0)
        new_bottom = clamp(bottom - dy, game_map.height - SCREEN_HEIGHT, 0)
        self.update_viewport_coordinates(new_bottom, new_left)

    def update_viewport_coordinates(self, new_bottom, new_left):
        new_right = new_left + SCREEN_WIDTH
        new_top = new_bottom + SCREEN_HEIGHT
        self.current_view.viewport = new_left, new_right, new_bottom, new_top
        self.set_viewport(new_left, new_right, new_bottom, new_top)
        if self.is_game_running:
            self.game_view.update_interface_position(new_right, new_top)

    def move_viewport_to_the_position(self, x: int, y: int):
        """
        Call it when Player clicked on the minimap or teleported to the
        position of selected permanent group of Units with numeric keys.
        """
        game_map = self.game_view.map
        new_left = clamp(x - SCREEN_X, game_map.width - SCREEN_WIDTH, 0)
        new_bottom = clamp(y - SCREEN_Y, game_map.height - SCREEN_HEIGHT, 0)
        left, _, bottom, _ = self.current_view.viewport
        self.update_viewport_coordinates(new_bottom, new_left)

    def get_viewport(self) -> Viewport:
        # We cache viewport coordinates each time they are changed,
        # so no need for redundant call to the Window method
        return self.current_view.viewport

    def save_game(self):
        # TODO: save GameObject.total_objects_count (?)
        self.save_manger.save_game('save_01', self.game_view)

    def load_game(self):
        if self.game_view is not None:
            self.game_view.unload()
            self.quit_current_game()
        self.game_view = Game(file_to_load_from='save_01')
        GameObject.total_objects_count = 0
        self.save_manger.load_game('save_01', self.game_view)

    def close(self):
        log(f'Terminating application...')
        super().close()


class Game(LoadableWindowView, EventsCreator, UiBundlesHandler):
    instance: Optional[Game] = None

    def __init__(self, file_to_load_from=None):
        LoadableWindowView.__init__(self)
        EventsCreator.__init__(self)
        UiBundlesHandler.__init__(self)
        self.file_to_load_from = file_to_load_from
        self.assign_reference_to_self_for_all_classes()

        self.settings = self.window.settings  # shared with Window class
        self.current_frame = 0

        # SpriteLists:
        self.terrain_tiles = SpriteListWithSwitch(is_static=True, update_on=False)
        self.vehicles_threads = SpriteList(is_static=True)
        self.units_ordered_destinations = UnitsOrderedDestinations()
        self.units = SelectiveSpriteList()
        self.static_objects = SpriteListWithSwitch(is_static=True, update_on=False)
        self.buildings = SelectiveSpriteList(is_static=True)
        self.effects = SpriteList(is_static=True)
        self.selection_markers_sprites = SpriteList()
        self.interface: UiSpriteList() = self.create_interface()
        self.set_updated_and_drawn_lists()

        self.map: Optional[Map] = None
        self.pathfinder: Optional[Pathfinder] = None

        self.fog_of_war: Optional[FogOfWar] = None

        # All GameObjects are initialized by the specialised factory:
        self.spawner: Optional[ObjectsFactory] = None

        self.explosions_pool: Optional[ExplosionsPool] = None

        self.mini_map: Optional[MiniMap] = None

        # Units belongs to the Players, Players belongs to the Factions, which
        # are updated each frame to evaluate AI, enemies-visibility, etc.
        self.factions: Dict[int, Faction] = {}
        self.players: Dict[int, Player] = {}

        self.local_human_player: Optional[Player] = None
        # We only draw those Units and Buildings, which are 'known" to the
        # local human Player's Faction or belong to it, the rest of entities
        # is hidden. This set is updated each frame:
        self.local_drawn_units_and_buildings: Set[PlayerEntity] = set()

        # Player can create group of Units by CTRL + 0-9 keys, and then
        # select those groups quickly with 0-9 keys, or even move screen tp
        # the position of the group by pressing numeric key twice. See the
        # PermanentUnitsGroup class in units_management.py
        self.permanent_units_groups: Dict[int, PermanentUnitsGroup] = {}

        self.mission: Optional[Mission] = None
        self.current_mission: Optional[Mission] = None

        self.debugged = []
        self.map_grid = None

        self.things_to_load = [
            ['map', Map, 0.35, {'rows': COLUMNS, 'columns': ROWS,
             'grid_width': TILE_WIDTH,'grid_height': TILE_HEIGHT}],
            ['pathfinder', Pathfinder, 0.05, lambda: self.map],
            ['fog_of_war', FogOfWar, 0.25],
            ['spawner', ObjectsFactory, 0.05, lambda: self.pathfinder, lambda: self.window.configs],
            ['explosions_pool', ExplosionsPool, 0.10],
            ['mini_map', MiniMap, 0.10],
            ['map_grid', self.create_map_debug_grid, 0.10]
        ] if self.file_to_load_from is None else []

    def assign_reference_to_self_for_all_classes(self):
        name = self.__class__.__name__.lower()
        for _class in (c for c in globals().values() if hasattr(c, name)):
            setattr(_class, name, self)
        Game.instance = self.window.cursor.game = self

    def create_interface(self) -> UiSpriteList:
        ui_x, ui_y = SCREEN_WIDTH * 0.9, SCREEN_Y
        ui_size = SCREEN_WIDTH // 5, SCREEN_HEIGHT
        right_ui_panel = Frame('ui_right_panel.png', ui_x, ui_y, *ui_size)
        right_panel = UiElementsBundle(
            name=BASIC_UI,
            index=0,
            elements=[
                right_ui_panel,
                Button('game_button_menu.png', ui_x, 100,
                       functions=partial(
                           self.window.show_view, self.window.menu_view),
                       parent=right_ui_panel),
                Button('game_button_pause.png', ui_x - 100, 100,
                       functions=partial(self.toggle_pause),
                       parent=right_ui_panel)
            ],
            register_to=self
        )
        units_panel = UiElementsBundle(
            name=UNITS_PANEL,
            index=1,
            elements=[
                Button('game_button_stop.png', ui_x - 100, 800,
                       functions=self.stop_all_units),
                Button('game_button_attack.png', ui_x, 800,
                       functions=partial(self.window.cursor.force_cursor, 2))
            ],
            register_to=self
        )
        biuilding_panel = UiElementsBundle(
            name=BUILDINGS_PANEL,
            index=2,
            elements=[
                Button('game_button_stop.png', ui_x, 800),
            ],
            register_to=self
        )

        editor_panel = UiElementsBundle(
            name=EDITOR,
            index=3,
            elements=[
                ScrollableContainer('ui_scrollable_frame.png', ui_x, ui_y,
                                    'scrollable'),
            ],
            register_to=self,
        )
        editor_panel.extend(
            [
                Button('small_button_none.png', ui_x, 100 * i,
                       parent=editor_panel.elements[0]) for i in range(5)
            ]
        )
        return self.ui_elements_spritelist  # UiBundlesHandler attribute

    def update_interface_position(self, right, top):
        diff_x = right - self.interface[0].right
        diff_y = top - self.interface[0].top
        self.interface.move(diff_x, diff_y)
        self.update_not_displayed_bundles_positions(-diff_x, -diff_y)
        self.mini_map.update_position(diff_x, diff_y)

    def update_interface_content(self, context=None):
        """
        Change elements displayed in interface to proper for currently selected
        gameobjects giving player access to context-options.
        """
        self._unload_all(exception=BASIC_UI)
        if context:
            if isinstance(context, Building):
                self.configure_building_interface(context)
            else:
                self.configure_units_interface(context)

    def configure_building_interface(self, context: Building):
        self.load_bundle(name=('%s' % BUILDINGS_PANEL))

    def configure_units_interface(self, context: List[Unit]):
        self.load_bundle(name=('%s' % UNITS_PANEL))
        self.load_bundle(name=EDITOR)

    def create_effect(self, effect_type: Any, name: str, x, y):
        """
        Add animated sprite to the self.effects spritelist to display e.g.:
        explosions.
        """
        if effect_type == Explosion:
            effect = self.explosions_pool.get(name, x, y)
        else:
            return
        self.effects.append(effect)
        effect.play()

    def on_show_view(self):
        super().on_show_view()
        self.window.toggle_mouse_and_keyboard(True)
        self.window.sound_player.play_playlist('game')
        self.update_interface_content()

    def test_methods(self):
        if self.file_to_load_from is None:
            self.test_scheduling_events()
            self.test_factions_and_players_creation()
            # self.test_buildings_spawning()
            self.test_units_spawning()
        position = average_position_of_points_group(
            [u.position for u in self.local_human_player.units]
        )
        self.window.move_viewport_to_the_position(*position)

    def test_scheduling_events(self):
        event = ScheduledEvent(self, 5, self.scheduling_test, repeat=True)
        self.schedule_event(event)

    def test_factions_and_players_creation(self):
        faction = Faction(name='Freemen')
        player = Player(id=2, color=RED, faction=faction)
        cpu_player = CpuPlayer(color=GREEN)
        self.local_human_player: Optional[Player] = self.players[2]
        player.start_war_with(cpu_player)

    def test_buildings_spawning(self):
        self.buildings.append(self.spawn(
            'medium_factory.png',
            self.players[2],
            (400, 600),
        ))

    def spawn(self,
              object_name: str,
              player: Union[Player, int],
              position: Point,
              id: Optional[int] = None) -> Optional[GameObject]:
        if (player := self.get_player_instance(player)) is not None:
            return self.spawner.spawn(object_name, player, position, id=id)
        return None

    def get_player_instance(self, player: Union[Player, int]):
        if isinstance(player, int):
            try:
                return self.players[player]
            except KeyError:
                return None
        return player

    def spawn_group(self,
                    names: List[str],
                    player: Union[Player, int],
                    position: Point):
        if (player := self.get_player_instance(player)) is not None:
            return self.spawner.spawn_group(names, player, position)
        return None

    def test_units_spawning(self):
        spawned_units = []
        unit_name = 'tank_medium.png'
        for player in (self.players.values()):
            node = random.choice(list(self.map.nodes.values()))
            names = [unit_name] * 20
            spawned_units.extend(
                self.spawn_group(names, player, node.position)
            )
        self.units.extend(spawned_units)

    def load_player_configs(self) -> Dict[str, Any]:
        configs: Dict[str, Any] = {}
        # TODO
        return configs

    @staticmethod
    def next_free_player_color() -> Color:
        return 0, 0, 0

    def register(self, acquired: OwnedObject):
        acquired: Union[Player, Faction, PlayerEntity, UiElementsBundle]
        if isinstance(acquired, GameObject):
            self.register_gameobject(acquired)
        elif isinstance(acquired, (Player, Faction)):
            self.register_player_or_faction(acquired)
        else:
            super().register(acquired)

    def register_gameobject(self, registered: GameObject):
        if isinstance(registered, PlayerEntity):
            if registered.is_building:
                self.buildings.append(registered)
            else:
                self.units.append(registered)
        else:
            self.terrain_tiles.append(registered)

    def register_player_or_faction(self, registered: Union[Player, Faction]):
        if isinstance(registered, Player):
            self.players[registered.id] = registered
        else:
            self.factions[registered.id] = registered

    def unregister(self, owned: OwnedObject):
        owned: Union[PlayerEntity, Player, Faction, UiElementsBundle]
        if isinstance(owned, GameObject):
            self.unregister_gameobject(owned)
        elif isinstance(owned, (Player, Faction)):
            self.unregister_player_or_faction(owned)
        else:
            super().unregister(owned)

    def unregister_gameobject(self, owned: GameObject):
        if isinstance(owned, PlayerEntity):
            if owned.is_building:
                self.buildings.remove(owned)
            else:
                self.units.remove(owned)
        else:
            self.terrain_tiles.remove(owned)

    def unregister_player_or_faction(self, owned: Union[Player, Faction]):
        if isinstance(owned, Player):
            del self.players[owned.id]
        else:
            del self.factions[owned.id]

    def get_notified(self, *args, **kwargs):
        pass

    def show_dialog(self, dialog_name: str):
        print(dialog_name)

    def update_view(self, delta_time):
        self.debugged.clear()
        super().update_view(delta_time)
        self.update_local_drawn_units_and_buildings()
        self.update_factions_and_players()
        self.fog_of_war.update()
        self.pathfinder.update()
        self.mini_map.update()

    def after_loading(self):
        self.window.show_view(self)
        self.test_methods()
        # we put FoW before the interface to list of rendered layers to
        # assure that FoW will not cover player interface:
        self.drawn.insert(-2, self.fog_of_war)
        super().after_loading()
        print(self.players[4].units)

    def update_local_drawn_units_and_buildings(self):
        """
        We draw on the screen only these PlayerEntities, which belongs to the
        local Player's Faction, or are detected by his Faction.
        """
        self.local_drawn_units_and_buildings.clear()
        local_faction = self.local_human_player.faction
        self.local_drawn_units_and_buildings.update(
            local_faction.units,
            local_faction.buildings,
            local_faction.known_enemies
        )

    def update_factions_and_players(self):
        for faction in self.factions.values():
            faction.update()

    @timer(level=1, global_profiling_level=PROFILING_LEVEL)
    def on_draw(self):
        super().on_draw()
        self.mini_map.draw()
        if self.settings.debug:
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
            draw_rectangle_filled(adj.x, adj.y, TILE_WIDTH, TILE_HEIGHT, color)
            draw_circle_outline(*adj.position, 5, color=WHITE, border_width=1)

    def draw_debugged(self):
        self.draw_debug_paths()
        self.draw_debug_lines_of_sight()
        self.draw_debug_units()

    def draw_debug_units(self):
        unit: Unit
        for unit in self.units:
            x, y = unit.position
            draw_text(str(unit.id), x, y + 40, color=GREEN)
            if (target := unit.targeted_enemy) is not None:
                draw_text(str(target.id), x, y - 40, color=RED)

    def draw_debug_paths(self):
        for path in (u.path for u in self.local_human_player.units if u.path):
            for i, point in enumerate(path):
                try:
                    end = path[i + 1]
                    draw_line(*point, *end, color=GREEN, line_width=1)
                except IndexError:
                    pass

    def draw_debug_lines_of_sight(self):
        for unit in (u for u in self.local_human_player.units if u.known_enemies):
            for enemy in unit.known_enemies:
                draw_line(*unit.position, *enemy.position, color=RED)

    def draw_paused_dialog(self):
        x, y = self.window.screen_center
        draw_rectangle_filled(x, y, SCREEN_WIDTH, 200, to_rgba(BLACK, 150))
        text = 'GAME PAUSED'
        draw_text(text, x, y, WHITE, 30, anchor_x='center', anchor_y='center')

    def toggle_pause(self):
        super().toggle_pause()
        self.window.toggle_mouse_and_keyboard(not self.paused, only_mouse=True)

    def create_map_debug_grid(self) -> arcade.ShapeElementList:
        grid = arcade.ShapeElementList()
        h_offset = TILE_HEIGHT // 2
        w_offset = TILE_WIDTH // 2
        # horizontal lines:
        for i in range(self.map.rows):
            y = i * TILE_HEIGHT
            h_line = create_line(0, y, self.map.width, y, BLACK)
            grid.append(h_line)

            y = i * TILE_HEIGHT + h_offset
            h2_line = create_line(w_offset, y, self.map.width, y, WHITE)
            grid.append(h2_line)
        # vertical lines:
        for j in range(self.map.columns * 2):
            x = j * TILE_WIDTH
            v_line = create_line(x, 0, x, self.map.height, BLACK)
            grid.append(v_line)

            x = j * TILE_WIDTH + w_offset
            v2_line = create_line(x, h_offset, x, self.map.height, WHITE)
            grid.append(v2_line)
        return grid

    def stop_all_units(self):
        for unit in self.window.cursor.selected_units:
            unit.stop_completely()

    def unload(self):
        for updated in (u for u in self.updated if isinstance(u, SpriteList)):
            updated = None
        self.local_human_player = None
        self.local_drawn_units_and_buildings.clear()
        self.factions.clear()
        self.players.clear()


if __name__ == '__main__':
    # these imports are placed here to avoid circular-imports issue:
    from map.map import Map, Pathfinder
    from units.unit_management import PermanentUnitsGroup, SelectedEntityMarker
    from effects.explosions import Explosion, ExplosionsPool
    from players_and_factions.player import (
        Faction, Player, CpuPlayer, PlayerEntity
    )
    from controllers.keyboard import KeyboardHandler
    from controllers.mouse import MouseCursor
    from units.units import Unit, UnitsOrderedDestinations
    from gameobjects.gameobject import GameObject
    from gameobjects.spawning import ObjectsFactory
    from map.fog_of_war import FogOfWar
    from buildings.buildings import Building
    from scenarios.missions import Mission
    from user_interface.menu import Menu
    from user_interface.minimap import MiniMap
    from persistency.save_handling import SaveManager

    if __status__ == 'development' and PYPROFILER:
        from pyprofiler import start_profile, end_profile
        with start_profile() as profiler:
            window = Window(SCREEN_WIDTH, SCREEN_HEIGHT, UPDATE_RATE)
            arcade.run()
        end_profile(profiler, 35, True)
    else:
        window = Window(SCREEN_WIDTH, SCREEN_HEIGHT, UPDATE_RATE)
        arcade.run()
