from enum import Enum
from collections import namedtuple

CorLoc = namedtuple("CorLoc", "from_x, from_y, to_x, to_y")
CrossLoc = namedtuple("CrossLoc", "x, y")
ShelfLoc = namedtuple("ShelfLoc", "x, y, slot, level")


class Orientation(Enum):
    UP = 1
    RIGHT = 2
    DOWN = 3
    LEFT = 4

def opposite_orientation(o):
    if o == Orientation.UP:
        return Orientation.DOWN
    elif o == Orientation.RIGHT:
        return Orientation.LEFT
    elif o == Orientation.DOWN:
        return Orientation.UP
    elif o == Orientation.LEFT:
        return Orientation.RIGHT

def road_orientation(cor_loc):
    if cor_loc.from_x == cor_loc.to_x:
        y_diff = cor_loc.to_y - cor_loc.from_y
        if y_diff == 1:
            return Orientation.DOWN
        elif y_diff == -1:
            return Orientation.UP
        else:
            raise Exception(str(cor_loc), "not permissible")
    elif cor_loc.from_y == cor_loc.to_y:
        x_diff = cor_loc.to_x - cor_loc.from_x
        if x_diff == 1:
            return Orientation.RIGHT
        elif x_diff == -1:
            return Orientation.LEFT
        else:
            raise Exception(str(cor_loc) + " not permissible")
    else:
        raise Exception(str(cor_loc) + " not permissible")

# return the relative orientation of point "to" with respect to point "from"
def relative_orientation(from_x, from_y, to_x, to_y):
    relative_orientations = []
    if to_x > from_x:
        relative_orientations.append(Orientation.RIGHT)
    elif to_x < from_x:
        relative_orientations.append(Orientation.LEFT)
    if to_y > from_y:
        relative_orientations.append(Orientation.DOWN)
    elif to_y < from_y:
        relative_orientations.append(Orientation.UP)
    return relative_orientations

def relative_orientation_and_distance(from_x, from_y, to_x, to_y):
    offset = {}
    if to_x > from_x:
        offset[Orientation.RIGHT] = to_x - from_x
    elif to_x < from_x:
        offset[Orientation.LEFT] = from_x - to_x
    if to_y > from_y:
        offset[Orientation.DOWN] = to_y - from_y
    elif to_y < from_y:
        offset[Orientation.UP] = from_y - to_y
    return offset
