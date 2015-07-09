from collections import namedtuple
from enum import Enum
from threading import Lock
from struct import pack
import sys

# define struct types
CorLoc = namedtuple("CorLoc", "from_x, from_y, to_x, to_y")
CrossLoc = namedtuple("CrossLoc", "x, y")
ShelfLoc = namedtuple("ShelfLoc", "x, y, slot, level")
class TaskType(Enum):
    TO_DOCK = 1
    FOR_CONTAINER = 2
Task = namedtuple("Task", "type, dest_dock_id, dest_container_id")
class Orientation(Enum):
    UP = 1
    RIGHT = 2
    DOWN = 3
    LEFT = 4
class Direction(Enum):
    STRAIGHT = 1
    TURN_LEFT = 2
    TURN_RIGHT = 3

# global variables
robot_position = {}
free_robots = []    # containing IPs of robots
                    # to be locked
robots_on_rest = []
free_list_lock = Lock()
pending_tasks = []  # containing Task type
                    #  to be locked
pending_lock = Lock()

################################### ROUTING ####################################

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

# WARNING: magic number
def is_road_legal(cor_loc):
    if not (cor_loc.from_x in range(0, 4) and cor_loc.to_x in range(0, 4) and cor_loc.from_y in range(0, 6)
            and cor_loc.to_y in range(0, 6)):
        return False
    orientation = road_orientation(cor_loc)
    if orientation == Orientation.UP or orientation == Orientation.DOWN:
        return True
    elif cor_loc.from_y == 0:
        return orientation == Orientation.RIGHT
    elif cor_loc.from_y == 1:
        return True
    else:
        return bool(cor_loc.from_y % 2) == (orientation == Orientation.RIGHT)

def orientation_after_turn(o, direction):
    if direction == Direction.STRAIGHT:
        return o
    elif direction == Direction.TURN_LEFT:
        if o == Orientation.UP:
            return Orientation.LEFT
        elif o == Orientation.RIGHT:
            return Orientation.UP
        elif o == Orientation.DOWN:
            return Orientation.RIGHT
        else:
            return Orientation.DOWN
    else:
        if o == Orientation.UP:
            return Orientation.RIGHT
        elif o == Orientation.RIGHT:
            return Orientation.DOWN
        elif o == Orientation.DOWN:
            return Orientation.LEFT
        else:
            return Orientation.UP

def opposite_orientation(o):
    if o == Orientation.UP:
        return Orientation.DOWN
    elif o == Orientation.RIGHT:
        return Orientation.LEFT
    elif o == Orientation.DOWN:
        return Orientation.UP
    elif o == Orientation.LEFT:
        return Orientation.RIGHT

# return the turning direction to turn from orientation o_from to o_to
def turn_direction_from_o_to_o(o_from, o_to):
    if o_from == o_to:
        return Direction.STRAIGHT
    elif (o_to.value - o_from.value) % 4 == 1:
        return Direction.TURN_RIGHT
    elif (o_to.value - o_from.value) % 4 == 3:
        return Direction.TURN_LEFT
    else:
        raise Exception("turn_from_o_to_o: cannot turnaround")

def road_after_go_in_orientations(src, o):
    if o == Orientation.UP:
        return CorLoc(src.to_x, src.to_y, src.to_x, src.to_y - 1)
    elif o == Orientation.RIGHT:
        return CorLoc(src.to_x, src.to_y, src.to_x + 1, src.to_y)
    elif o == Orientation.DOWN:
        return CorLoc(src.to_x, src.to_y, src.to_x, src.to_y + 1)
    else:
        return CorLoc(src.to_x, src.to_y, src.to_x - 1, src.to_y)

def road_after_forward_steps(src, forward_step_number):
    current_orientation = road_orientation(src)
    if current_orientation == Orientation.UP:
        dest = CorLoc(src.from_x, src.from_y - forward_step_number, src.to_x, src.to_y - forward_step_number)
    elif current_orientation == Orientation.RIGHT:
        dest = CorLoc(src.from_x + forward_step_number, src.from_y, src.to_x + forward_step_number, src.to_y)
    elif current_orientation == Orientation.DOWN:
        dest = CorLoc(src.from_x, src.from_y + forward_step_number, src.to_x, src.to_y + forward_step_number)
    else:
        dest = CorLoc(src.from_x - forward_step_number, src.from_y, src.to_x - forward_step_number, src.to_y)
    return dest

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

# c1 and c2 are two crossing points
# they must be in a line
def one_way_distance(c1_x, c1_y, c2_x, c2_y):
    deviation_direction = relative_orientation(c1_x, c1_y, c2_x, c2_y)
    if len(deviation_direction) != 1:
        raise Exception("one_way_distance:", c1_x, c2_x, "and", c2_x, c2_y, "are not in a straight line")
    if deviation_direction[0] == Orientation.UP:
        return c1_y - c2_y
    elif deviation_direction[0] == Orientation.RIGHT:
        return c2_x - c1_x
    elif deviation_direction[0] == Orientation.DOWN:
        return c2_y - c1_y
    else:
        return c1_x - c2_x


def route_road_to_road(src, dest):
    current_orientation = road_orientation(src)
    aiming_orientation = relative_orientation(src.to_x, src.to_y, dest.from_x, dest.from_y)
    # if dest.from is along the driving direction
    if current_orientation in aiming_orientation:
        # if dest.from is off the enlongated line
        if len(aiming_orientation) == 2:
            aiming_orientation.remove(current_orientation)
            deviated_orientation = aiming_orientation[0]
            distance_offset = relative_orientation_and_distance(src.to_x, src.to_y, dest.from_x, dest.from_y)
            # try to go straight until perpendicular to dest.from
            # if can turn to the deviated direction then, go straight and turn
            forward_step_till_perpendicular = distance_offset[current_orientation]
            final_src = road_after_go_in_orientations(road_after_forward_steps(src, forward_step_till_perpendicular),
                                                           deviated_orientation)
            if is_road_legal(final_src):
                return [Direction.STRAIGHT.value] * forward_step_till_perpendicular \
                       + [turn_direction_from_o_to_o(current_orientation, deviated_orientation).value] \
                       + route_road_to_road(final_src, dest)
            # otherwise turn in advance
            elif forward_step_till_perpendicular >= 1:
                forward_steps = forward_step_till_perpendicular - 1
                final_src = road_after_go_in_orientations(road_after_forward_steps(src, forward_steps),
                                                           deviated_orientation)
                return [Direction.STRAIGHT.value] * forward_steps \
                       + [turn_direction_from_o_to_o(current_orientation, deviated_orientation).value] \
                       + route_road_to_road(final_src, dest)
            else:
                raise Exception("route_road_to_road: shouldn't be possible")

        # if dest.from is on the enlongated line, go straight until reached dest.from
        else:
            forward_step_number = one_way_distance(src.from_x, src.from_y, dest.from_x, dest.from_y) - 1
            final_src = road_after_forward_steps(src, forward_step_number)
            return [Direction.STRAIGHT.value] * forward_step_number + route_road_to_road(final_src, dest)

    # if dest.from is opposite the driving direction
    elif opposite_orientation(current_orientation) in aiming_orientation:
        # if dest.from is off the oppositely elongated line
        if len(aiming_orientation) == 2:
            aiming_orientation.remove(opposite_orientation(current_orientation))
            deviated_orientation = aiming_orientation[0]
            # if can turn into the deviated orientation, turn
            if is_road_legal(road_after_go_in_orientations(src, deviated_orientation)):
                new_orientation = deviated_orientation
            # if can go straight, go
            elif is_road_legal(road_after_go_in_orientations(src, current_orientation)):
                new_orientation = current_orientation
            # otherwise, do the only left option
            else:
                new_orientation = opposite_orientation(deviated_orientation)
            return [turn_direction_from_o_to_o(current_orientation, new_orientation).value] \
                   + route_road_to_road(road_after_go_in_orientations(src, new_orientation), dest)

        # if dest.from is on the oppositely elongated line
        else:
            dest_orientation = road_orientation(dest)
            # if dest has orientation perpendicular to src
            if dest_orientation not in [current_orientation, opposite_orientation(current_orientation)]:
                # if can turn into the opposite direction of "dest", turn
                if is_road_legal(road_after_go_in_orientations(src, opposite_orientation(dest_orientation))):
                    new_orientation = opposite_orientation(dest_orientation)
                # otherwise, turn into the other direction (the same with "dest")
                else:
                    new_orientation = dest_orientation
            # otherwise
            else:
                # if can turn right, turn right; if not, turn left
                turn_right_orientation = orientation_after_turn(current_orientation, Direction.TURN_RIGHT)
                if is_road_legal(road_after_go_in_orientations(src, turn_right_orientation)):
                    new_orientation = turn_right_orientation
                else:
                    new_orientation = opposite_orientation(turn_right_orientation)
            return [turn_direction_from_o_to_o(current_orientation, new_orientation).value] \
                   + route_road_to_road(road_after_go_in_orientations(src, new_orientation), dest)

    # if dest.from is perpendicular to the driving direction
    else:
        # if we have reached dest.from, we're almost there [base case]
        if dest.from_x == src.to_x and dest.from_y == src.to_y:
            if dest.to_x != src.from_x or dest.to_y != src.from_y:
                return [turn_direction_from_o_to_o(current_orientation, road_orientation(dest)).value]
            else:
                raise Exception("route_road_to_road: strict turnaround, fail")
        else:
            deviated_orientation = aiming_orientation[0]
            # if can turn into the deviated orientation, turn
            if is_road_legal(road_after_go_in_orientations(src, deviated_orientation)):
                new_orientation = deviated_orientation
            # if can go straight, go
            elif is_road_legal(road_after_go_in_orientations(src, current_orientation)):
                new_orientation = current_orientation
            # otherwise, do the only left option
            else:
                new_orientation = opposite_orientation(deviated_orientation)
            return [turn_direction_from_o_to_o(current_orientation, new_orientation).value] \
                   + route_road_to_road(road_after_go_in_orientations(src, new_orientation), dest)

def route_corridor_to_dock(cor_loc, dock_id):
    print("corridor", cor_loc, "to dock", dock_id)
    if dock_id == 0:
        half_dest = CorLoc(0, 1, 0, 0)
    elif dock_id == 1:
        half_dest = CorLoc(1, 1, 1, 0)
    elif dock_id == 2:
        half_dest = CorLoc(2, 1, 2, 0)
    else:
        raise Exception("route_corridor_to_dock: invalid dock_id", dock_id)
    route = route_road_to_road(cor_loc, half_dest) + [Direction.TURN_RIGHT.value]
    return route

def corridor_on_shelf_to_left(shelf_loc):
    if shelf_loc.y % 2 == 0:
        return CorLoc(shelf_loc.x + 1, shelf_loc.y, shelf_loc.x, shelf_loc.y)
    else:
        return CorLoc(shelf_loc.x + 1, shelf_loc.y + 1, shelf_loc.x, shelf_loc.y + 1)
def corridor_on_shelf_to_right(shelf_loc):
    if shelf_loc.y % 2 == 0:
        return CorLoc(shelf_loc.x, shelf_loc.y + 1, shelf_loc.x + 1, shelf_loc.y + 1)
    else:
        return CorLoc(shelf_loc.x, shelf_loc.y, shelf_loc.x + 1, shelf_loc.y)

def route_corridor_to_shelf(cor_loc, shelf_loc):
    print("corridor", cor_loc, "to shelf", shelf_loc)
    if cor_loc.to_x <= shelf_loc.x:
        shelf_corloc = corridor_on_shelf_to_right(shelf_loc)
        last_road_orientation = Orientation.RIGHT
    else:
        shelf_corloc = corridor_on_shelf_to_left(shelf_loc)
        last_road_orientation = Orientation.LEFT
    return route_road_to_road(cor_loc, shelf_corloc), last_road_orientation
    # TODO: which direction to load, shelf slot, level

# return the route, and orientation of the last piece of the route
def route_dock_to_shelf(dock_id, shelf_loc):
    print("dock", dock_id, "to shelf", shelf_loc)
    if dock_id == 0:
        half_src = CorLoc(1, 0, 1, 1)
    elif dock_id == 1:
        half_src = CorLoc(2, 0, 2, 1)
    elif dock_id == 2:
        half_src = CorLoc(3, 0, 3, 1)
    else:
        raise Exception("route_dock_to_shelf: invalid dock_id", dock_id)
    (half_route, last_road_orientation) = route_corridor_to_shelf(half_src, shelf_loc)
    return [Direction.TURN_RIGHT.value] + half_route, last_road_orientation

def compile_route(route):
    return pack("B" * (len(route) + 1), len(route), *route)

################################### DISTANCE ESTIMATION ####################################

def dis_corridor_to_shelf(cor_loc, shelf_loc):
    print("distance of corridor to shelf")
    return 42

def dis_corridor_to_dock(cor_loc, dock_id):
    print("distance of corridor to dock")
    return 42

################################### NEAREST ####################################

# return "" if no free robots at the moment
def nearest_free_robot_to_dock(dock_id):
    print("nearest robot to dock #" + str(dock_id))
    # if there's no free robot, add the task to pending list
    free_list_lock.acquire()
    if len(free_robots) == 0:
        pending_lock.acquire()
        pending_tasks.append(Task(TaskType.TO_DOCK, dock_id, 0))
        pending_lock.release()
        free_list_lock.release()
        return ""
    # find the nearest among the free robots
    smallest_distance = sys.maxsize
    chosen_robot_ip = ""
    for ip, loc in robot_position.items():
        distance = dis_corridor_to_dock(loc, dock_id)
        if distance < smallest_distance:
            smallest_distance = distance
            chosen_robot_ip = ip
    free_robots.remove(chosen_robot_ip)
    free_list_lock.release()
    return chosen_robot_ip

def pend_fetching_task_to(container_id, dock_id):
    pending_lock.acquire()
    pending_tasks.append(Task(TaskType.FOR_CONTAINER, dock_id, container_id))
    pending_lock.release()
# return "" if no free robots at the moment
def nearest_free_robot_to_shelf(shelf_loc, container_id, dock_id):
    print("nearest robot to shelf")
    # if there's no free robot, add the task to pending list
    free_list_lock.acquire()
    if len(free_robots) == 0:
        pend_fetching_task_to(container_id, dock_id)
        free_list_lock.release()
        return ""
    # find the nearest among the free robots
    smallest_distance = sys.maxsize
    chosen_robot_ip = ""
    for ip, loc in robot_position.items():
        distance = dis_corridor_to_shelf(loc, shelf_loc)
        if distance < smallest_distance:
            smallest_distance = distance
            chosen_robot_ip = ip
    free_robots.remove(chosen_robot_ip)
    free_list_lock.release()
    return chosen_robot_ip

def nearest_empty_shelf_slot(dock_id):
    # TODO
    return (1, 1, 1, 1)

################################### TOP LEVEL ####################################

def update_robot_pos(robot_ip, row, col):
    robot_position[robot_ip] = CorLoc(row, col)

def get_robot_pos(robot_ip):
    return robot_position[robot_ip]

# return a task for the free robot to perform
# or return None when there's no suitable task and the robot is added to the free list
def add_free_robot(robot_ip):
    with free_list_lock, pending_lock:
        # if there's pending task to do, assign the first to this robot
        if len(pending_tasks) != 0:
            task = pending_tasks.pop(0)
            # TODO: check if the task is performable (?)
            # if there's FETCHING job where container is TO_SHELF or TO_IMPORT, get it done with that carrier robot
            return task
        # otherwise, add the robot to free list
        else:
            free_robots.append(robot_ip)
            return None
