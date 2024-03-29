from utility_types import *
from socket_utility import *
import db_manager
import planning
import highway
from struct import *
import os
from socket import *


# command 0 []
def request_robot(conn, addr):
    print("Tachikoma!")
    worker_ip = addr[0]
    dock_id = db_manager.get_dock_id_by_ip(worker_ip)
    responsible_robot_ip = planning.nearest_free_robot_to_dock(dock_id)
    if responsible_robot_ip != "":
        planning.robot_perform_task(responsible_robot_ip, planning.Task(planning.TaskType.TO_DOCK, dock_id, 0))
        print(responsible_robot_ip, "is called")

# command 1 [item_id]
def request_item(conn, addr):
    worker_ip = addr[0]
    dock_id = db_manager.get_dock_id_by_ip(worker_ip)
    # receive the rest of the message
    data = receive_message(conn, 1)
    item_id = unpack("B", data)[0]
    print("Please fetch me item #" + str(item_id))
    # get info about the container
    result = db_manager.locate_item(item_id)
    if not result:
        # the item does not exist, reply to the app [6]
        send_message(worker_sockets[dock_id], pack("B", 6))
        return
    (container_id, row, col, slot, level, status) = result
    # tell the worker app in which container the requested item is
    send_message(worker_sockets[dock_id], pack("BB", 4, container_id))
    # if the container is going to PACKING dock or has been reserved, we can't do it now
    if status == "TO_PACKING" or status == "RESERVED":
        planning.pend_fetching_task_to(container_id, dock_id)
    # if the container is on shelf, try to find the nearest robot to fetch it and carry to the dock
    elif status == "ON_SHELF":
        responsible_robot_ip = planning.nearest_free_robot_to_shelf(ShelfLoc(row, col, slot, level),
                                                                    container_id, dock_id)
        if responsible_robot_ip != "":
            planning.robot_perform_task(responsible_robot_ip,
                               planning.Task(planning.TaskType.FOR_CONTAINER, dock_id, container_id))
    # if the container is to IMPORT dock or is TO_SHELF, call the robot over
    elif status == "TO_SHELF":
        responsible_robot_ip = db_manager.get_container_carrier(container_id)
        planning.robot_perform_task(responsible_robot_ip, planning.Task(planning.TaskType.TO_DOCK, dock_id, 0))
        # update bookkeeping
        db_manager.set_container_status(container_id, "TO_PACKING")
    # TODO: if called over TO_IMPORT, need to call someone else to that IMPORT dock
    # TODO: or maybe not, because for the moment there can be no container being carried TO_IMPORT anyway
    else:
        raise Exception("request_item: item cannot possibly TO_IMPORT")

# command 2 []
def robot_join(conn, addr):
    print("Robot " + addr[0] + " request to join the network")
    robot_ip = addr[0]
    # log the socket
    robot_sockets[robot_ip] = conn
    # WARNING: magic number
    # TODO: more plan on what to do
    planning.update_robot_pos(robot_ip, 0, 0, 1, 0)
    planning.robot_enter_rest(robot_ip)
    db_manager.robot_join(addr[0])
    conn.sendall(pack("B", 3))
    # tell it where to go
    # if there's no task, just do nothing
    assigned_task = planning.add_free_robot(robot_ip)
    if assigned_task is not None:
        planning.robot_perform_task(robot_ip, assigned_task)

# command 3 [new_from_x, new_from_y, new_to_x, new_to_y]
def robot_update_pos(conn, addr):
    robot_ip = addr[0]
    # read new position (row, col)
    data = receive_message(conn, 4)
    (from_x, from_y, to_x, to_y) = unpack("B" * 4, data)
    print("Robot", robot_ip, "now arrives", (from_x, from_y, to_x, to_y))
    planning.update_robot_pos(robot_ip, from_x, from_y, to_x, to_y)

# command 4 []
def container_fetched(conn, addr):
    robot_ip = addr[0]
    print("Robot", robot_ip, "got his hand on his container")
    dest_dock_id = db_manager.container_off_shelf(robot_ip)
    # give route to the robot to report back to the requesting dock
    robot_pos = planning.get_robot_pos(robot_ip)
    route = planning.route_corridor_to_dock(robot_pos, dest_dock_id)
    print("Report back to dock ", dest_dock_id, "en route", route)
    message = pack("B" * 6, 0, 1, robot_pos.from_x, robot_pos.from_y, robot_pos.to_x, robot_pos.to_y)
    message += planning.compile_route(route)
    status = planning.send_route(robot_ip, message)
    # the robot cannot possibly have moved
    assert not status, "container_fetched: robot not at its position, impossible case"

# command 5 []
def container_stored(conn, addr):
    print("Robot " + addr[0] + " said goodbye to his container")
    robot_ip = addr[0]
    db_manager.update_container_pos(robot_ip)
    # tell it where to go next
    assigned_task = planning.add_free_robot(robot_ip)
    if assigned_task is None:
        planning.robot_go_idle(robot_ip)
    else:
        planning.robot_perform_task(robot_ip, assigned_task)

# command 6 [from_x, from_y, to_x, to_y]
def apply_crossing(conn, addr):
    robot_ip = addr[0]
    data = receive_message(conn, 4)
    (from_x, from_y, to_x, to_y) = unpack("BBBB", data)
    print("Robot " + robot_ip + " apply to enter crossing")
    highway.apply_crossing(robot_ip, CorLoc(from_x, from_y, to_x, to_y), conn)

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
    data = receive_message(conn, 2)
    (item_id, container_id) = unpack("BB", data)
    # register the info in DB
    db_manager.check_in_item(item_id, container_id)
    print("Item #" + str(item_id) + " has been put into container #" + str(container_id))

# command 10 [item ID]
def check_out(conn, addr):
    robot_ip = addr[0]
    data = receive_message(conn, 1)
    item_id = unpack("B", data)[0]
    # delete the item from DB
    db_manager.check_out_item(item_id)
    print("Item #" + str(item_id) + " has been checked out")

# command 11 [from_x, from_y, to_x, to_y, is_grasper_left]
def arrive_dock(conn, addr):
    robot_ip = addr[0]
    data = receive_message(conn, 5)
    (from_x, from_y, to_x, to_y, is_grasper_left) = unpack("B" * 5, data)
    # interpret which dock has been arrived
    assert (from_x, from_y, to_x, to_y) in [(1, 0, 2, 0), (2, 0, 3, 0)], "arrive_dock: reported position not at a dock"
    if (from_x, from_y, to_x, to_y) == (1, 0, 2, 0):
        dock_id = 1
        # tell the corresponding worker app that a robot has arrived
        send_message(worker_sockets[dock_id], pack("B", 0))
    elif (from_x, from_y, to_x, to_y) == (2, 0, 3, 0):
        dock_id = 2
        # tell the corresponding worker app that a robot has arrived, and which container it is carrying
        container_id = db_manager.get_container_on_robot(robot_ip)
        send_message(worker_sockets[dock_id], pack("BB", 5, container_id))
    db_manager.robot_arrive_dock(dock_id, robot_ip, is_grasper_left)
    print("Robot " + addr[0] + " has arrived at dock #" + str(dock_id))

# command 12 [container_id]
def dismiss_robot(conn, addr):
    container_id = unpack("B", receive_message(conn, 1))[0]
    dock_id = db_manager.get_dock_id_by_ip(addr[0])
    # find where the grasper for the robot is
    is_grasper_right = db_manager.is_on_dock_robot_grasper_on_right(dock_id)
    # decouple the robot from the dock
    robot_ip = db_manager.robot_leave_dock(dock_id)
    # tell the robot which container it is carrying
    # if the container has already been taken away, mark the robot free
    container_exist = db_manager.set_robot_container(robot_ip, container_id)
    if not container_exist:
        assigned_task = planning.add_free_robot(robot_ip)
        if assigned_task is None:
            planning.robot_go_idle(robot_ip)
        else:
            planning.robot_perform_task(robot_ip, assigned_task)
        return
    # otherwise
    # find the nearest empty shelf slot for the robot to put its container
    # send the route to this robot
    (x, y, slot, level) = planning.nearest_empty_shelf_slot(dock_id, is_grasper_right)
    (route, last_road_orientation) = planning.route_dock_to_shelf(dock_id, ShelfLoc(x, y, slot, level))
    print("robot", robot_ip, "dismissed to", ShelfLoc(x, y, slot, level), "en route", route)
    if dock_id == 1:
        robot_pos = CorLoc(1, 0, 2, 0)
    elif dock_id == 2:
        robot_pos = CorLoc(2, 0, 3, 0)
    else:
        raise Exception("dismiss_robot: robot", robot_ip, "dismissed from unknown dock #", dock_id)
    message = planning.compile_to_shelf_message(robot_pos, route, last_road_orientation, x, y, slot, level, True)
    status = planning.send_route(robot_ip, message)
    # the robot cannot possibly have moved
    assert not status, "dismiss_robot: robot has moved, impossible case"
    # update bookkeeping
    db_manager.set_robot_dest_shelf(robot_ip, x, y, slot, level)
    db_manager.update_container_dest(container_id, x, y, slot, level)
    # TODO: if PACKING, tell worker app to disable "dismiss" button (maybe not?)
    print("Robot " + addr[0] + " is dismissed")

# command 13 [dock_id]
def worker_join(conn, addr):
    data = receive_message(conn, 1)
    dock_id = unpack("B", data)[0]
    result = db_manager.worker_join(dock_id, addr[0])
    if result:
        print("Worker " + addr[0] + " has occupied dock #" + str(dock_id))
        send_message(conn, pack("B", 2))
        worker_sockets[dock_id] = conn
    else:
        print("Dock #" + str(dock_id) + " already occupied. Request Denied")
        send_message(conn, pack("B", 3))

# command 14 []
def worker_leave(conn, addr):
    dock_id = db_manager.worker_leave(addr[0])
    del worker_sockets[dock_id]
    print("Worker " + addr[0] + " is now off duty")

# command 15 []
def arrive_rest(conn, addr):
    print("Robot", addr[0], "has arrived REST top")

# command 16 []
def receive_heartbeat(conn, addr):
    pass

def robot_leave(robot_ip):
    db_manager.robot_leave(robot_ip)
    del robot_sockets[robot_ip]
    planning.delete_robot(robot_ip)
    highway.delete_robot_from_crossings(robot_ip)


command_funcs = [request_robot, request_item, robot_join, robot_update_pos, container_fetched, container_stored,
                 apply_crossing, alarm_report, cancel_alarm, check_in, check_out, arrive_dock, dismiss_robot,
                 worker_join, worker_leave, arrive_rest, receive_heartbeat]
