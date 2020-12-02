#!/usr/bin/env python

import os
import shelve

from typing import Dict
from abc import abstractmethod

from utils.classes import Singleton
from utils.functions import log, find_paths_to_all_files_of_type
from utils.data_types import SavedGames

SAVE_EXTENSION = '.sav'
SCENARIO_EXTENSION = '.scn'


class SaveManager(Singleton):
    """
    This manager works not only with player-created saved games, but also with
    predefined scenarios stored in the same file-format, but in ./scenarios
    direction.
    """

    def __init__(self, saves_path: str, scenarios_path: str):
        self.scenarios_path = scenarios_path = os.path.abspath(scenarios_path)
        self.path_to_saves = saves_path = os.path.abspath(saves_path)

        self.scenarios = self.find_all_scenarios(SCENARIO_EXTENSION, scenarios_path)
        self.saved_games = self.find_all_game_saves(SAVE_EXTENSION, saves_path)

        log(f'Found {len(self.saved_games)} saved games in {self.path_to_saves}.')

    @staticmethod
    def find_all_scenarios(extension: str, path: str) -> SavedGames:
        names_to_paths = find_paths_to_all_files_of_type(extension, path)
        return {
            name: os.path.join(path, name) for name, path in names_to_paths.items()
        }

    @staticmethod
    def find_all_game_saves(extension: str, path: str) -> SavedGames:
        names_to_paths = find_paths_to_all_files_of_type(extension, path)
        return {
            name: os.path.join(path, name) for name, path in names_to_paths.items()
        }

    def save_game(self, save_name: str, game: 'Game'):
        full_save_path = os.path.join(self.path_to_saves, save_name)
        with shelve.open(full_save_path + SAVE_EXTENSION) as file:
            file['map'] = game.map
            file['mission'] = game.mission
            file['factions'] = [faction for faction in game.factions]
            file['players'] = [player for player in game.players]
            file['units'] = [unit for unit in game.units]
            file['buildings'] = [building for building in game.buildings]
            file['permanent_units_groups'] = game.permanent_units_groups
            file['fog_of_war'] = game.fog_of_war
            file['mini_map'] = game.mini_map

    def load_game(self, save_name: str):
        raise NotImplementedError

    def delete_saved_game(self, save_name: str):
        try:
            os.remove(self.saved_games[save_name])
            del self.saved_games[save_name]
        except FileNotFoundError:
            pass

    def rename_saved_game(self, old_name: str, new_name: str):
        try:
            new = os.path.join(self.path_to_saves, new_name) + SAVE_EXTENSION
            os.rename(self.saved_games[old_name], new)
            self.saved_games[new_name] = new
            del self.saved_games[old_name]
        except Exception as e:
            log(f'{str(e)}', console=True)
