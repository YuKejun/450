from utility_types import *
from socket_utility import *
import highway
import db_manager
from collections import namedtuple
from enum import Enum
from threading import Lock
from struct import pack, unpack
import sys

# define struct types
class TaskType(Enum):
    TO_DOCK = 1
    FOR_CONTAINER = 2
Task = namedtuple("Task", "type, dest_dock_id, dest_container_id")
class Direction(Enum):
    STRAIGHT = 1
    TURN_LEFT = 2
    TURN_RIGHT = 3

# global variables
robot_position = {}
free_robots = []    # containing IPs of robots
                    # to be locked
free_list_lock = Lock()
robots_on_rest = []
rest_lock = Lock()
pending_tasks = []  # containing Task type
                    #  to be locked
pending_lock = Lock()

################################### ROUTING ####################################

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
    # special cases: robot in REST area is called to IMPORT dock
    if cor_loc == CorLoc(0, 1, 0, 0) and dock_id == 1:
        return [Direction.TURN_RIGHT.value, Direction.STRAIGHT.value]
    if cor_loc == CorLoc(0, 0, 1, 0) and dock_id == 1:
        return [Direction.STRAIGHT.value]
    assert cor_loc not in [CorLoc(0, 1, 0, 0), CorLoc(0, 0, 1, 0)], \
        "route_corridor_to_dock: robot in REST cannot be called to dock other than IMPORT"
    # special cases: robot just left IMPORT dock is called to PACKING
    if cor_loc == CorLoc(1, 0, 2, 0) and dock_id == 2:
        return [Direction.STRAIGHT.value]
    assert cor_loc != CorLoc(1, 0, 2, 0) or dock_id == 0, "route_corridor_to_dock: robot in IMPORT cannot be called"
    # normal cases
    if dock_id == 0:
        half_dest = CorLoc(0, 1, 0, 0)
    elif dock_id == 1:
        half_dest = CorLoc(1, 1, 1, 0)
    elif dock_id == 2:
        half_dest = CorLoc(2, 1, 2, 0)
    else:
        raise Exception("route_corridor_to_dock: invalid dock_id", dock_id)
    return route_road_to_road(cor_loc, half_dest) + [Direction.TURN_RIGHT.value]

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
    # special cases: the robot is in REST area
    if cor_loc == CorLoc(0, 0, 1, 0):
        return route_dock_to_shelf(0, shelf_loc)
    elif cor_loc == CorLoc(0, 1, 0, 0):
        (route, last_road_orientation) = route_dock_to_shelf(0, shelf_loc)
        return [Direction.TURN_RIGHT.value] + route, last_road_orientation
    elif cor_loc == CorLoc(1, 0, 2, 0):
        return route_dock_to_shelf(1, shelf_loc)
    elif cor_loc == CorLoc(2, 0, 3, 0):
        return route_dock_to_shelf(2, shelf_loc)
    # this function cannot be called in worker dock area
    assert cor_loc not in [CorLoc(1, 1, 1, 0), CorLoc(2, 1, 2, 0)], "route_corridor_to_shelf: cannot be planned from dock area"
    # normal cases
    if cor_loc.to_x <= shelf_loc.x:
        shelf_corloc = corridor_on_shelf_to_right(shelf_loc)
        last_road_orientation = Orientation.RIGHT
    else:
        shelf_corloc = corridor_on_shelf_to_left(shelf_loc)
        last_road_orientation = Orientation.LEFT
    return route_road_to_road(cor_loc, shelf_corloc), last_road_orientation

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

def compile_to_shelf_message(robot_pos, route, last_road_orientation, shelf_x, shelf_y, shelf_slot, shelf_level, is_store):
    message = pack("B" * 6, 0, 0, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
    message += compile_route(route)
    if last_road_orientation == Orientation.LEFT:
        running_slot = 1 - shelf_slot
    else:
        running_slot = shelf_slot
    left_right = shelf_y % 2
    message += pack("B" * 4, running_slot, shelf_level, left_right, is_store)
    return message

################################### DISTANCE ESTIMATION ####################################

def dis_estimate_deviation(from_x, from_y, to_x, to_y):
    distance = 0
    deviation = relative_orientation_and_distance(from_x, from_y, to_x, to_y)
    if Orientation.UP in deviation.keys():
        distance += 2 * deviation[Orientation.UP]
    if Orientation.DOWN in deviation.keys():
        distance += 2 * deviation[Orientation.DOWN]
    if Orientation.RIGHT in deviation.keys():
        distance += 3 * deviation[Orientation.RIGHT]
    if Orientation.LEFT in deviation.keys():
        distance += 3 * deviation[Orientation.LEFT]
    return distance

def dis_estimate_corridor_to_corridor(corloc1, corloc2):
    distances = []
    distances.append(dis_estimate_deviation(corloc1.from_x, corloc1.from_y, corloc2.from_x, corloc2.from_y))
    distances.append(dis_estimate_deviation(corloc1.to_x, corloc1.to_y, corloc2.from_x, corloc2.from_y))
    distances.append(dis_estimate_deviation(corloc1.from_x, corloc1.from_y, corloc2.to_x, corloc2.to_y))
    distances.append(dis_estimate_deviation(corloc1.to_x, corloc1.to_y, corloc2.to_x, corloc2.to_y))
    return max(distances)

def dis_estimate_corridor_to_shelf(cor_loc, shelf_x, shelf_y):
    return dis_estimate_corridor_to_corridor(CorLoc(shelf_x, shelf_y, shelf_x+1, shelf_y), cor_loc)

def dis_estimate_corridor_to_dock(cor_loc, dock_id):
    assert dock_id == 1 or dock_id == 2, "dis_estimate_corridor_to_dock: invalid dock_id " + str(dock_id)
    if dock_id == 1:
        dock_corloc = CorLoc(1, 0, 2, 0)
    elif dock_id == 2:
        dock_corloc = CorLoc(2, 0, 3, 0)
    return dis_estimate_corridor_to_corridor(cor_loc, dock_corloc)

def dis_estimate_dock_to_shelf(dock_id, shelf_x, shelf_y):
    assert dock_id == 1 or dock_id == 2, "dis_estimate_corridor_to_dock: invalid dock_id " + str(dock_id)
    if dock_id == 1:
        dock_corloc = CorLoc(1, 0, 2, 0)
    elif dock_id == 2:
        dock_corloc = CorLoc(2, 0, 3, 0)
    return dis_estimate_corridor_to_shelf(dock_corloc, shelf_x, shelf_y)

################################### NEAREST ####################################

# return "" if no free robots at the moment, and the task will be added into pending list
def nearest_free_robot_to_dock(dock_id):
    print("nearest robot to dock #" + str(dock_id))
    # if there's no free robot, add the task to pending list
    with free_list_lock:
        if len(free_robots) == 0:
            with pending_lock:
                pending_tasks.append(Task(TaskType.TO_DOCK, dock_id, 0))
            return ""
        # find the nearest among the free robots
        smallest_distance = sys.maxsize
        chosen_robot_ip = ""
        for ip in free_robots:
            distance = dis_estimate_corridor_to_dock(robot_position[ip], dock_id)
            if distance < smallest_distance:
                smallest_distance = distance
                chosen_robot_ip = ip
        # if the robot is in REST area, call the line head instead
        print("before try:", chosen_robot_ip, robots_on_rest)
        chosen_robot_ip = try_call_rest_robot(chosen_robot_ip)
        print("after try:", chosen_robot_ip, robots_on_rest)
        # mark the chosen robot busy
        free_robots.remove(chosen_robot_ip)
        return chosen_robot_ip

def pend_fetching_task_to(container_id, dock_id):
    with pending_lock:
        pending_tasks.append(Task(TaskType.FOR_CONTAINER, dock_id, container_id))

# return "" if no free robots at the moment
def nearest_free_robot_to_shelf(shelf_loc, container_id, dock_id):
    '''
    Find the nearest free robot to a shelf. If the chosen robot in REST area, choose the line head. If none free, add a FOR_CONTAINER task to pending list

    :return: The chosen robot ip. If none, return ""
    '''
    print("nearest robot to shelf", shelf_loc)
    with free_list_lock:
        # if there's no free robot, add the task to pending list
        if len(free_robots) == 0:
            pend_fetching_task_to(container_id, dock_id)
            return ""
        # find the nearest among the free robots
        smallest_distance = sys.maxsize
        chosen_robot_ip = ""
        for ip in free_robots:
            distance = dis_estimate_corridor_to_shelf(robot_position[ip], shelf_loc.x, shelf_loc.y)
            if distance < smallest_distance:
                smallest_distance = distance
                chosen_robot_ip = ip
        # if the robot is in REST area, call the line head instead
        chosen_robot_ip = try_call_rest_robot(chosen_robot_ip)
        # mark the chosen robot busy
        free_robots.remove(chosen_robot_ip)
        return chosen_robot_ip

def nearest_empty_shelf_slot(dock_id, grasper_on_right):
    shelves = []
    for x in range(3):
        for y in range(2 + int(grasper_on_right), 5, 2):
            shelves.append((x, y))
    shelves.sort(key = lambda s: dis_estimate_dock_to_shelf(dock_id, s[0], s[1]))
    print("shelves in order", shelves)
    for (x, y) in shelves:
        empty_slots = db_manager.empty_slots_of_shelf(x, y)
        if len(empty_slots) == 0:
            continue
        return x, y, empty_slots[0][0], empty_slots[0][1]


################################### REST ####################################

def robot_enter_rest(robot_ip):
    print("robot", robot_ip, "enters REST area")
    with rest_lock:
        assert robot_ip not in robots_on_rest, "robot_rest: robot " + robot_ip + " already in REST area"
        robots_on_rest.append(robot_ip)

# if the given robot is in REST area, return the robot at the head of the REST line instead,
# and label that robot out of line
# otherwise, return the same robot
def try_call_rest_robot(robot_ip):
    with rest_lock:
        if robot_ip in robots_on_rest:
            print("current rest line:", robots_on_rest)
            print("A robot chosen out of REST area")
            return robots_on_rest.pop(0)
        else:
            return robot_ip


################################### TOP LEVEL ####################################

def update_robot_pos(robot_ip, from_x, from_y, to_x, to_y):
    robot_position[robot_ip] = CorLoc(from_x, from_y, to_x, to_y)
    highway.update_robot_position_for_crossing(robot_ip, CorLoc(from_x, from_y, to_x, to_y))
    # if the robot is entering REST area, log it
    if (from_x, from_y, to_x, to_y) == (0, 1, 0, 0):
        robot_enter_rest(robot_ip)

def get_robot_pos(robot_ip):
    return robot_position[robot_ip]

################################### TASK MANAGEMENT ####################################

# send new route to the robot, and waits for reply
# return None if everything OK
# otherwise return the actual position of the robot
def send_route(robot_ip, message):
    robot_sockets[robot_ip].sendall(message)
    # wait till get confirmation from robot
    data = receive_message(robot_sockets[robot_ip], 1)
    reply_status = unpack("B", data)[0]
    if reply_status == 1:
        print("send_route: route received successfully")
        return None
    # if the robot is not at what I expect it to be
    # receive an updated position
    elif reply_status == 0:
        data = receive_message(robot_sockets[robot_ip], 4)
        (from_x, from_y, to_x, to_y) = unpack("B" * 4, data)
        print("send_route: route received, position change to", (from_x, from_y, to_x, to_y))
        return CorLoc(from_x, from_y, to_x, to_y)
    else:
        raise Exception("send_route: unknown reply status", reply_status)

# send new route
# (maybe) set dest_dock
def robot_go_idle(robot_ip):
    robot_pos = get_robot_pos(robot_ip)
    while True:
        route = route_corridor_to_dock(robot_pos, 0)
        print("robot", robot_ip, "go idle from", robot_pos, "en route", route)
        message = pack("B" * 6, 0, 2, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
        message += compile_route(route)
        robot_pos = send_route(robot_ip, message)
        if not robot_pos:
            break
        update_robot_pos(robot_ip, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)

def robot_perform_task(robot_ip, task):
    # send new route to the robot
    robot_pos = get_robot_pos(robot_ip)
    if task.type == TaskType.TO_DOCK:
        # send robot the route it needs to trace
        while True:
            route = route_corridor_to_dock(robot_pos, task.dest_dock_id)
            print("robot", robot_ip, "at", robot_pos, task, route)
            message = pack("B" * 6, 0, 1, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
            message += compile_route(route)
            robot_pos = send_route(robot_ip, message)
            if not robot_pos:
                break
            update_robot_pos(robot_ip, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
        # update bookkeeping
        db_manager.set_robot_dest_dock(robot_ip, task.dest_dock_id)
    else:  # task.type == planning.TaskType.FOR_CONTAINER
        # get info about the container
        (container_id, x, y, slot, level, status) = db_manager.get_container_info(task.dest_container_id)
        if status == "ON_SHELF":
            # send new route to the robot
            while True:
                (route, last_road_orientation) \
                    = route_corridor_to_shelf(robot_pos, ShelfLoc(x, y, slot, level))
                print("robot", robot_ip, "at", robot_pos, task, route)
                message = compile_to_shelf_message(robot_pos, route, last_road_orientation, x, y, slot, level, False)
                robot_pos = send_route(robot_ip, message)
                if not robot_pos:
                    break
                update_robot_pos(robot_ip, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
            # update bookkeeping
            db_manager.set_robot_dest_dock(robot_ip, task.dest_dock_id)
            db_manager.set_robot_dest_shelf(robot_ip, x, y, slot, level)
            db_manager.set_robot_container(robot_ip, task.dest_container_id)
            db_manager.set_container_status(container_id, "RESERVED")
        else:
            raise Exception("robot_perform_task: Container #", container_id, " is not on shelf. Cannot fetch")

# return a task for the free robot to perform
# or return None when there's no suitable task and the robot is added to the free list
def add_free_robot(robot_ip):
    with free_list_lock, pending_lock:
        i = 0
        while i < len(pending_tasks):
            task = pending_tasks[i]
            if task.type == TaskType.FOR_CONTAINER:
                (container_id, row, col, slot, level, status) = db_manager.get_container_info(task.dest_container_id)
                # if the task is a FETCHING job where the requested container is TO_SHELF,
                # re-assign task to that robot TO_PACKING
                if status == "TO_SHELF":
                    carrier_robot_ip = db_manager.get_container_carrier(task.dest_container_id)
                    robot_perform_task(carrier_robot_ip, Task(TaskType.TO_DOCK, task.dest_dock_id, 0))
                    # update bookkeeping
                    db_manager.set_container_status(container_id, "TO_PACKING")
                    pending_tasks.pop(i)
                    continue
                # if the task is a FETCHING job where the requested container is TO_IMPORT,
                # re-assign task to that robot TO_PACKING
                # and let this newly added robot to the TO_IMPORT instead
                elif status == "TO_IMPORT":
                    carrier_robot_ip = db_manager.get_container_carrier(task.dest_container_id)
                    destined_import_dock_id = db_manager.get_robot_dest_dock(carrier_robot_ip)
                    robot_perform_task(carrier_robot_ip, Task(TaskType.TO_DOCK, task.dest_dock_id, 0))
                    db_manager.set_container_status(container_id, "TO_PACKING")
                    pending_tasks.pop(i)
                    return Task(TaskType.TO_DOCK, destined_import_dock_id, 0)
                # if the task is a FETCHING job where the requested container is RESERVED or TO_PACKING,
                # it cannot be done now, skip, try the next task
                elif status == "RESERVED" or status == "TO_PACKING":
                    i += 1
                    continue
            # otherwise, the task is do-able, assign it to this newly added robot
            pending_tasks.pop(i)
            return task
        # if there's no task can be done, add the robot to free list
        free_robots.append(robot_ip)
        return None

def delete_robot(robot_ip):
    with rest_lock, free_list_lock:
        if robot_ip in robots_on_rest:
            robots_on_rest.remove(robot_ip)
        if robot_ip in free_robots:
            free_robots.remove(robot_ip)

