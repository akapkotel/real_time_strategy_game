#!/usr/bin/env python

import logging

from math import hypot, atan2, degrees, sin, cos, radians
from time import perf_counter
from numba import njit
from shapely import speedups, affinity
from shapely.geometry import LineString, Polygon

from arcade.arcade_types import RGB, RGBA

from typing import Sequence, Tuple, List, Iterable, Any
from data_types import Point, Number, Union


speedups.enable()

logging.basicConfig(
    filename='resources/logfile.txt',
    filemode='w',
    level=logging.INFO,
    format='%(levelname)s: %(asctime)s %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p'
)


def log(logged_message: str, console: Union[int, bool] = False):
    if console:
        print(logged_message)
        logging.warning(logged_message)
    else:
        logging.info(logged_message)


def timer(level=0, global_profiling_level=0, forced=False):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if forced or level > global_profiling_level:
                return func(*args, **kwargs)

            start_time = perf_counter()
            result = func(*args, **kwargs)
            end_time = perf_counter()

            execution_time = end_time - start_time
            fps = 1 / execution_time
            fr = f"{func.__name__} finished in {execution_time:.4f} secs. FPS:{fps}"
            log(fr, console=level)
            return result
        return wrapper
    return decorator


def get_screen_size() -> Tuple:
    # import platform

    from PIL import ImageGrab
    screen = ImageGrab.grab()
    return int(screen.width), int(screen.height)


def filter_sequence(sequence: Sequence,
                    filtered_class: Any) -> List[Any]:
    return [s for s in sequence if isinstance(s, filtered_class)]


def first_object_of_type(iterable: Iterable, class_name: type(object)):
    """
    Search the <iterable> for first instance of object which class is named
    <class_name>.
    """
    for obj in iterable:
        if isinstance(obj, class_name):
            return obj


def get_attributes_with_attribute(instance: object, name: str,
                                  ignore: Tuple = ()) -> List:
    """
    Search all attributes of <instance> to find all objects which have their
    own attribute of <name> and return these objects as List. You can also add
    a Tuple od class names to be ignored during query.
    """
    attributes = instance.__dict__.values()
    return [
        attr for attr in attributes if hasattr(attr, name) and not isinstance(attr, ignore)
    ]


def average_position_of_points_group(positions: Sequence[Point]) -> Point:
    """
    :param positions: Sequence -- array of Points (x, y)
    :return: Point -- two-dimensional tuple (x, y) representing point
    """
    positions_count = len(positions)
    if positions_count == 1:
        return positions[0]
    sum_x, sum_y = 0, 0
    for position in positions:
        sum_x += position[0]
        sum_y += position[1]
    return sum_x / positions_count, sum_y / positions_count


def get_path_to_file(filename: str) -> str:
    """
    Build full absolute path to the filename and return it + /filename.
    """
    import os
    for directory in os.walk(os.getcwd() + '/resources'):
        if filename in directory[2]:
            return f'{directory[0]}/{filename}'


def get_object_name(filename: str) -> str:
    """
    Retrieve raw name of a GameObject from the absolute path to it's texture.
    """
    name_with_extension = remove_path_from_name(filename)
    return name_with_extension.split('.', 1)[0]


def remove_path_from_name(filename):
    return filename.rsplit('/', 1)[1]


def object_name_to_filename(object_name: str) -> str:
    return '.'.join((object_name, '.png'))


def clamp(value: Number, maximum: Number, minimum: Number = 0) -> Number:
    """Guarantee that number will by larger than min and less than max."""
    return max(minimum, min(value, maximum))


def get_enemies(war: int) -> Tuple[int, int]:
    """
    Since each Player id attribute is a power of 2, id's can
    be combined to sum, being an unique identifier, for eg.
    Player with id 8 and Player with id 128 make unique sum
    136. To save pairs of hostile Players you can sum their
    id's and this function allows to retrieve pair from the
    saved value. Limit of Players in game is 16, since 2^32
    gives 8589934592, which is highest id checked by function.
    """
    index = 8589934592  # 2 to power of 32
    while index > 2:
        if war < index:
            index = index >> 1
        else:
            break
    return index, war - index


def to_rgba(color: RGB, alpha: int) -> RGBA:
    return color[0], color[1], color[2], alpha


@njit
def calculate_angle(sx: float, sy: float, ex: float, ey: float) -> float:
    """
    Calculate angle in direction from 'start' to the 'end' point in degrees.

    :param:sx float -- x coordinate of start point
    :param:sy float -- y coordinate of start point
    :param:ex float -- x coordinate of end point
    :param:ey float -- y coordinate of end point
    :return: float -- degrees in range 0-360.
    """
    radians = atan2(ex - sx, ey - sy)
    return -degrees(radians) % 360


def distance_2d(coord_a: Point, coord_b: Point) -> float:
    """Calculate distance between two points in 2D space."""
    return hypot(coord_b[0] - coord_a[0], coord_b[1] - coord_a[1])


def close_enough(coord_a: Point, coord_b: Point, distance: float) -> bool:
    """
    Calculate distance between two points in 2D space and find if distance
    is less than minimum distance.

    :param coord_a: Point -- (x, y) coords of first point
    :param coord_b: Point -- (x, y) coords of second point
    :param distance: float -- minimal distance to check against
    :return: bool -- if distance is less than
    """
    return distance_2d(coord_a, coord_b) <= distance


@njit
def vector_2d(angle: float, scalar: float) -> Point:
    """
    Calculate x and y parts of the current vector.

    :param angle: float -- angle of the vector
    :param scalar: float -- scalar difference of the vector (e.g. speed)
    :return: Point -- x and y parts of the vector in format: (float, float)
    """
    rad = -radians(angle)
    return sin(rad) * scalar, cos(rad) * scalar


def visible(position_a: Point, position_b: Point, obstacles_: List) -> bool:
    """
    Check if position_a is 'visible' from position_b and vice-versa. 'Visible'
    means, that you can connect both points with straight line without
    intersecting any obstacle.

    :param position_a: tuple -- coordinates of first position (x, y)
    :param position_b: tuple -- coordinates of second position (x, y)
    :param obstacles_: list -- Obstacle objects to check against
    :return: tuple -- (bool, list)
    """
    if not obstacles_: return True
    line = LineString([position_a, position_b])
    return not any((Polygon(o.points).crosses(line) for o in obstacles_))