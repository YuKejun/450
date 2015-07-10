from threading import Lock
from enum import Enum
from collections import namedtuple
from socket import *
from struct import *
import planning

class HighwayType(Enum):
    HORIZONTAL = 0
    VERTICAL = 1

RobotInfo = namedtuple("RobotInfo", "corloc, socket")

class HighwayManager:
    def __init__(self, highway_type, number):
        self.type = highway_type
        self.number = number

        self.occupant_robots = {}
        self.occupant_lock = Lock()
        self.waiting_robots = {}
        self.waiting_lock = Lock()

    def is_corloc_on_highway(self, corloc):
        if self.type == HighwayType.HORIZONTAL:
            return corloc.from_y == self.number and corloc.to_y == self.number
        else:
            return corloc.from_x == self.number and corloc.to_x == self.number

    # WARNING: must hold occupant.lock when calling this function
    # robots are not allowed into the crossing if it is ahead of any occupants, or within one block behind any occupants
    # if the robot occupant is crossing the road, it locks up two adjacent blocks
    # return True if the robot is disallowed into the crossing
    def does_contradict_with_occupants(self, entering_crossloc):
        if self.type == HighwayType.HORIZONTAL:
            assert entering_crossloc.x == self.number, "HighwayManager::does_contradict_with_occupant: wrong call"
            for robot_ip in self.occupant_robots.keys():
                robot_orientation = planning.road_orientation(self.occupant_robots[robot_ip].corloc)
                if robot_orientation == planning.Orientation.LEFT:
                    if entering_crossloc.x <= self.occupant_robots[robot_ip].corloc.from_x + 1:
                        return True
                elif robot_orientation == planning.Orientation.RIGHT:
                    if entering_crossloc.x >= self.occupant_robots[robot_ip].corloc.from_x - 1:
                        return True
                else:
                    if self.occupant_robots[robot_ip].corloc.from_x - 1 \
                            <= entering_crossloc.x <= self.occupant_robots[robot_ip].corloc.from_x + 1:
                        return True
            return False
        else:
            assert entering_crossloc.y == self.number, "HighwayManager::does_contradict_with_occupant: wrong call"
            for robot_ip in self.occupant_robots.keys():
                robot_orientation = planning.road_orientation(self.occupant_robots[robot_ip].corloc)
                if robot_orientation == planning.Orientation.UP:
                    if entering_crossloc.y <= self.occupant_robots[robot_ip].corloc.from_y + 1:
                        return True
                elif robot_orientation == planning.Orientation.DOWN:
                    if entering_crossloc.y >= self.occupant_robots[robot_ip].corloc.from_y - 1:
                        return True
                else:
                    if self.occupant_robots[robot_ip].corloc.from_y - 1 \
                            <= entering_crossloc.y <= self.occupant_robots[robot_ip].corloc.from_y + 1:
                        return True
            return False

    def apply_crossing(self, robot_ip, corloc, socket):
        if self.type == HighwayType.HORIZONTAL:
            assert (corloc.to_y == self.number
                    and planning.road_orientation(corloc) in [planning.Orientation.UP, planning.Orientation.DOWN]), \
                "HighwayManagger::apply_crossing: apply to the wrong crossing"
        else:
            assert (corloc.to_x == self.number
                    and planning.road_orientation(corloc) in [planning.Orientation.LEFT, planning.Orientation.RIGHT]), \
                "HighwayManagger::apply_crossing: apply to the wrong crossing"

        with self.occupant_lock, self.waiting_lock:
            assert robot_ip not in self.occupant_robots.keys() and robot_ip not in self.waiting_robots.keys(), \
                "HighwayManagger::apply_crossing: impossible application"
            # if the applicant is currently not allowed into the crossing, add it to waiting list
            if self.does_contradict_with_occupants(planning.CrossLoc(corloc.to_x, corloc.to_y)):
                self.waiting_robots[robot_ip] = RobotInfo(corloc, socket)
            # otherwise, notify it that it can go, and add it to occupant list
            else:
                socket.send(pack("B", 1))
                print("roobt", robot_ip, "is permitted into crossing", self.number)
                self.occupant_robots[robot_ip] = RobotInfo(corloc, socket)

    def let_waiting_go(self):
        with self.waiting_lock:
            for robot_ip in self.waiting_robots.keys():
                if not self.does_contradict_with_occupants(planning.CrossLoc(self.waiting_robots[robot_ip].corloc.to_x,
                                                                         self.waiting_robots[robot_ip].corloc.to_y)):
                    self.waiting_robots[robot_ip].socket.send(pack("B", 1))
                    print("roobt", robot_ip, "is permitted into crossing", self.number)
                    self.occupant_robots[robot_ip] = self.waiting_robots[robot_ip]
                    del self.waiting_robots[robot_ip]

    def update_robot_position(self, robot_ip, new_corloc):
        with self.occupant_lock:
            if robot_ip in self.occupant_robots.keys():
                # if the occupant is still on this highway, update its position, and check if we can let any waiting in
                if self.is_corloc_on_highway(new_corloc):
                    self.occupant_robots[robot_ip] = RobotInfo(new_corloc, self.occupant_robots[robot_ip].socket)
                    self.let_waiting_go()
                # otherwise, the occupant is leaving the highway
                # delete it, and check if we can let any waiting in
                else:
                    del self.occupant_robots[robot_ip]
                    self.let_waiting_go()

highways = {}
highways["H1"] = HighwayManager(HighwayType.HORIZONTAL, 1)
highways["V0"] = HighwayManager(HighwayType.VERTICAL, 0)
highways["V1"] = HighwayManager(HighwayType.VERTICAL, 1)
highways["V2"] = HighwayManager(HighwayType.VERTICAL, 2)
highways["V3"] = HighwayManager(HighwayType.VERTICAL, 3)

def apply_crossing(robot_ip, corloc, socket):
    if planning.road_orientation(corloc) in [planning.Orientation.UP, planning.Orientation.DOWN]:
        highway_code = "H" + corloc.to_x
    else:
        highway_code = "V" + corloc.to_y
    highways[highway_code].apply_crossing(robot_ip, corloc, socket)

def update_robot_position_for_crossing(robot_ip, new_corloc):
    for highway_manager in highways.values():
        highway_manager.update_robot_position(robot_ip, new_corloc)