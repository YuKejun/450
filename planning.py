from collections import namedtuple
from enum import Enum
from threading import Lock
import sys

# define struct types
CorLoc = namedtuple("CorLoc", "row, col")
ShelfLoc = namedtuple("ShelfLoc", "row, col, slot, level")
class TaskType(Enum):
    TO_DOCK = 1
    FOR_CONTAINER = 2
Task = namedtuple("Task", "type, dest_dock_id, dest_container_id")

# global variables
robot_position = {}
free_robots = []    # containing IPs of robots
                    # to be locked
free_list_lock = Lock()
pending_tasks = []  # containing Task type
                    #  to be locked
pending_lock = Lock()

################################### ROUTING ####################################

def route_corridor_to_shelf(cor_loc, shelf_loc):
    print("corridor to shelf")
    return b""

def route_corridor_to_dock(cor_loc, dock_id):
    print("corridor to dock")
    return b""

def route_dock_to_shelf(dock_id, shelf_loc):
    print("dock to shelf")
    return b""

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
