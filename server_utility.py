import db_manager
from planning import TaskType
import planning
from struct import *
import os
from socket import *

# global variables
robot_sockets = {}  # IP -> socket
worker_sockets = {}  # worker_id -> socket

def send_route(robot_ip, message):
    # TODO: loop till all sent
    robot_sockets[robot_ip].send(message)
    # wait till get confirmation from robot
    data = robot_sockets[robot_ip].recv(1)
    reply_status = unpack("B", data)[0]
    if reply_status == 1:
        return None
    # if the robot is not at what I expect it to be
    # receive an updated position
    elif reply_status == 0:
        data = robot_sockets[robot_ip].recv(4)
        (from_x, from_y, to_x, to_y) = unpack("B" * 4, data)
        return planning.CorLoc(from_x, from_y, to_x, to_y)
    else:
        raise Exception("send_route: unknown reply status", reply_status)

# send new route
# (maybe) set dest_dock
def robot_go_idle(robot_ip):
    robot_pos = planning.get_robot_pos(robot_ip)
    while True:
        route = planning.route_corridor_to_dock(robot_pos, 0)
        print("robot", robot_ip, "go idle from", robot_pos, "en route", route)
        message = pack("B" * 6, 0, 2, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
        message += planning.compile_route(route)
        robot_pos = send_route(robot_ip, message)
        if not robot_pos:
            break
        planning.update_robot_pos(robot_ip, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)

def compile_to_shelf_message(robot_pos, route, last_road_orientation, shelf_x, shelf_y, shelf_slot, shelf_level):
    message = pack("B" * 6, 0, 0, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
    message += planning.compile_route(route)
    if last_road_orientation == planning.Orientation.LEFT:
        running_slot = 1 - shelf_slot
    else:
        running_slot = shelf_slot
        left_right = shelf_y % 2
    message += pack("B" * 4, running_slot, shelf_level, left_right, 0)
    return message

def robot_perform_task(robot_ip, task):
    # send new route to the robot
    robot_pos = planning.get_robot_pos(robot_ip)
    if task.type == planning.TaskType.TO_DOCK:
        # send robot the route it needs to trace
        while True:
            route = planning.route_corridor_to_dock(robot_pos, task.dest_dock_id)
            print("robot", robot_ip, "at", robot_pos, task, route)
            message = pack("B" * 6, 0, 1, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
            message += planning.compile_route(route)
            robot_pos = send_route(robot_ip, message)
            if not robot_pos:
                break
            planning.update_robot_pos(robot_ip, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
        # update bookkeeping
        db_manager.set_robot_dest_dock(robot_ip, task.dest_dock_id)
    else:  # task.type == planning.TaskType.FOR_CONTAINER
        # get info about the container
        (container_id, x, y, slot, level, status) = db_manager.get_container_info(task.dest_container_id)
        if status == "ON_SHELF":
            # send new route to the robot
            while True:
                (route, last_road_orientation) \
                    = planning.route_corridor_to_shelf(robot_pos, planning.ShelfLoc(x, y, slot, level))
                print("robot", robot_ip, "at", robot_pos, task, route)
                message = compile_to_shelf_message(robot_pos, route, last_road_orientation, x, y, slot, level)
                robot_pos = send_route(robot_ip, message)
                if not robot_pos:
                    break
                planning.update_robot_pos(robot_ip, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
            # update bookkeeping
            db_manager.set_robot_dest_dock(robot_ip, task.dest_dock_id)
            db_manager.set_robot_dest_shelf(robot_ip, x, y, slot, level)
            db_manager.set_container_status(container_id, "RESERVED")
        else:
            raise Exception("robot_perform_task: Container #", container_id, " is not on shelf. Cannot fetch")


# command 0 []
def request_robot(conn, addr):
    print("Tachikoma!")
    worker_ip = addr[0]
    dock_id = db_manager.get_dock_id_by_ip(worker_ip)
    responsible_robot_ip = planning.nearest_free_robot_to_dock(dock_id)
    if responsible_robot_ip != "":
        robot_perform_task(responsible_robot_ip, planning.Task(planning.TaskType.TO_DOCK, dock_id, 0))

# command 1 [item_id]
def request_item(conn, addr):
    worker_ip = addr[0]
    dock_id = db_manager.get_dock_id_by_ip(worker_ip)
    # receive the rest of the message
    data = conn.recv(1)
    item_id = unpack("B", data)[0]
    print("Please fetch me item #" + str(item_id))
    # get info about the container
    (container_id, row, col, slot, level, status) = db_manager.locate_item(item_id)
    # if the container is going to PACKING dock or has been reserved, we can't do it now
    if status == "TO_PACKING" or status == "RESERVED":
        planning.pend_fetching_task_to(container_id, dock_id)
    # if the container is on shelf, try to find the nearest robot to fetch it and carry to the dock
    elif status == "ON_SHELF":
        responsible_robot_ip = planning.nearest_free_robot_to_shelf(planning.ShelfLoc(row, col, slot, level),
                                                                    container_id, dock_id)
        if responsible_robot_ip != "":
            robot_perform_task(responsible_robot_ip,
                               planning.Task(planning.TaskType.FOR_CONTAINER, dock_id, container_id))
    # if the container is to IMPORT dock or is TO_SHELF, call the robot over
    else:
        responsible_robot_ip = db_manager.get_container_carrier(container_id)
        robot_perform_task(responsible_robot_ip, planning.Task(planning.TaskType.TO_DOCK, dock_id, 0))
        # update bookkeeping
        db_manager.set_container_status(container_id, "TO_PACKING")

# command 2 []
def robot_join(conn, addr):
    print("Robot " + addr[0] + " request to join the network")
    robot_ip = addr[0]
    # log the socket
    robot_sockets[robot_ip] = conn
    db_manager.robot_join(addr[0])
    # tell it where to go
    assigned_task = planning.add_free_robot(robot_ip)
    if assigned_task is None:
        robot_go_idle(robot_ip)
    else:
        robot_perform_task(robot_ip, assigned_task)

# command 3 [new_from_x, new_from_y, new_to_x, new_to_y]
def robot_update_pos(conn, addr):
    robot_ip = addr[0]
    # read new position (row, col)
    data = conn.recv(4)
    (from_x, from_y, to_x, to_y) = unpack("B" * 4, data)
    print("Robot " + robot_ip + " now arrives (", from_x, from_y, to_x, to_y, ")")
    planning.update_robot_pos(robot_ip, from_x, from_y, to_x, to_y)

# command 4 []
def container_fetched(conn, addr):
    print("Robot " + addr[0] + " got his hand on his container")
    robot_ip = addr[0]
    dest_dock_id = db_manager.container_off_shelf(robot_ip)
    # give route to the robot to report back to the requesting dock
    robot_pos = planning.get_robot_pos(robot_ip)
    route = planning.route_corridor_to_dock(robot_pos, dest_dock_id)
    print(route)
    message = pack("B" * 6, 0, 1, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
    message += planning.compile_route(route)
    status = send_route(robot_ip, message)
    # the robot cannot possibly have moved
    if status:
        raise Exception("container_fetched: robot not at its position, impossible case")

# command 5 []
def container_stored(conn, addr):
    print("Robot " + addr[0] + " said goodbye to his container")
    robot_ip = addr[0]
    db_manager.update_container_pos(robot_ip)
    # tell it where to go next
    assigned_task = planning.add_free_robot(robot_ip)
    if assigned_task is None:
        robot_go_idle(robot_ip)
    else:
        robot_perform_task(robot_ip, assigned_task)

# command 6 [crossing_row, crossing_col, bound_direction]
def apply_crossing(conn, addr):
    data = conn.recv(3)
    data_list = unpack("BBB", data)
    print("Robot " + addr[0] + " apply to enter crossing " + str(data_list))
    # TODO

# command 7 []
def alarm_report(conn, addr):
    for i in range(1, 5):
        os.system('afplay /System/Library/Sounds/Submarine.aiff')
    # TODO: broadcast stopping command to everyone
    print("A~~~L~~~A~~~R~~~M~~~~")

# command 8 []
def cancel_alarm(conn, addr):
    print("Everything's good, back to work")
    # TODO

# command 9 [item ID, container ID]
def check_in(conn, addr):
    # receive further info
    data = conn.recv(2)
    data_list = unpack("BB", data)
    item_id = data_list[0]
    container_id = data_list[1]
    # register the info in DB
    db_manager.check_in_item(item_id, container_id)
    print("Item #" + str(item_id) + " has been put into container #" + str(container_id))

# command 10 [package ID]
def check_out(conn, addr):
    robot_ip = addr[0]
    data = conn.recv(1)
    item_id = unpack("B", data)[0]
    # delete the item from DB
    container_empty = db_manager.check_out_item(item_id)
    if container_empty:
        # TODO: decouple the robot from this dock
        # the robot is dismissed FREE
        # find a place for it to go
        assigned_task = planning.add_free_robot(robot_ip)
        if assigned_task is None:
            robot_go_idle(robot_ip)
        else:
            robot_perform_task(robot_ip, assigned_task)
        # TODO: tell worker app to disable "dismiss" button
    print("Item #" + str(item_id) + " has been checked out")

# command 11 [dock_id]
def arrive_dock(conn, addr):
    data = conn.recv(1)
    dock_id = unpack("B", data)[0]
    db_manager.robot_arrive_dock(dock_id, addr[0])
    # TODO: if PACKING, tell worker app to enable "dismiss" button
    print("Robot " + addr[0] + " has arrived at dock #" + str(dock_id))

# command 12 []
def dismiss_robot(conn, addr):
    dock_id = db_manager.get_dock_id_by_ip(addr[0])
    # find the nearest empty shelf slot for the robot to put its container
    # send the route to this robot
    (x, y, slot, level) = planning.nearest_empty_shelf_slot(dock_id)
    robot_ip = db_manager.robot_leave_dock(dock_id)
    (route, last_road_orientation) = planning.route_dock_to_shelf(dock_id, planning.ShelfLoc(x, y, slot, level))
    print("robot", robot_ip, "dismissed to", planning.ShelfLoc(x, y, slot, level), "en route", route)
    if dock_id == 1:
        robot_pos = planning.CorLoc(1, 0, 2, 0)
    elif dock_id == 2:
        robot_pos = planning.CorLoc(2, 0, 3, 0)
    else:
        raise Exception("dismiss_robot: robot", robot_ip, "dismissed from unknown dock #", dock_id)
    message = compile_to_shelf_message(robot_pos, route, last_road_orientation, x, y, slot, level)
    status = send_route(robot_ip, message)
    # the robot cannot possibly have moved
    if status:
        raise Exception("dismiss_robot: robot has moved, impossible case")
    # update bookkeeping
    db_manager.set_robot_dest_shelf(robot_ip, x, y, slot, level)
    container_id = db_manager.get_container_on_robot(robot_ip)
    db_manager.update_container_dest(container_id, x, y, slot, level)
    # TODO: if PACKING, tell worker app to disable "dismiss" button
    print("Robot " + addr[0] + " is dismissed")

# command 13 [dock_id]
def worker_join(conn, addr):
    data = conn.recv(1)
    dock_id = unpack("B", data)[0]
    result = db_manager.worker_join(dock_id, addr[0])
    if result:
        print("Worker " + addr[0] + " has occupied dock #" + str(dock_id))
    else:
        # TODO: reply to the worker app
        print("Dock #" + str(dock_id) + " already occupied. Request Denied")

# command 14 []
def worker_leave(conn, addr):
    db_manager.worker_leave(addr[0])
    print("Worker " + addr[0] + " is now off duty")


command_funcs = [request_robot, request_item, robot_join, robot_update_pos, container_fetched, container_stored,
                 apply_crossing, alarm_report, cancel_alarm, check_in, check_out, arrive_dock, dismiss_robot,
                 worker_join, worker_leave]
