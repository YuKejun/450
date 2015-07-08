import pymysql

HOST = 'localhost'
USER = 'Tachikoma'
DB = 'Tachikoma'

LAST_IMPORT_DOCK = 5

################################### WORKER ####################################

def worker_join(dock_id, worker_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # if the dock is being used, reject the request
    cursor.execute("SELECT COUNT(*) FROM Docks WHERE dock_id=(%s)", dock_id)
    if cursor.fetchone()[0] != 0:
        cursor.close()
        db.close()
        return False
    # register this worker on this dock
    dock_type = "IMPORT"
    if dock_id > LAST_IMPORT_DOCK:
        dock_type = "PACKING"
    cursor.execute("INSERT INTO Docks (dock_id, dock_type, worker_ip) VALUES (%s, %s, %s)",
                   (dock_id, dock_type, worker_ip))
    # cleanup
    cursor.close()
    db.commit()
    db.close()
    return True

def worker_leave(worker_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # delete the worker-dock relationship if there's one
    cursor.execute("SELECT COUNT(*) FROM Docks WHERE worker_ip=(%s)", worker_ip)
    if cursor.fetchone()[0] != 0:
        cursor.execute("DELETE FROM Docks WHERE worker_ip=(%s)", worker_ip)
    # cleanup
    cursor.close()
    db.commit()
    db.close()

################################### DOCKS ####################################

def get_dock_id_by_ip(worker_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("SELECT dock_id FROM Docks WHERE worker_ip=(%s)", worker_ip)
    if cursor.rowcount == 0:
        raise Exception("Worker " + worker_ip + " is not registered")
    dock_id = cursor.fetchone()[0]
    cursor.close()
    db.commit()
    db.close()
    return dock_id

def robot_arrive_dock(dock_id, robot_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # TODO: error: dock not in use; dock already occupied
    # verify that the robot is at the right dock
    cursor.execute("SELECT dest_dock_id FROM Robots WHERE robot_ip=(%s)", robot_ip)
    if cursor.fetchone()[0] != dock_id:
        # TODO: let somebody know?
        raise Exception("Robot arrives at the wrong dock")
    # let the dock aware of the new robot arriving
    cursor.execute("UPDATE Docks SET robot_ip=(%s) WHERE dock_id=(%s)", (robot_ip, dock_id))
    cursor.close()
    db.commit()
    db.close()

# return: IP of the robot at this dock when the function is called
def robot_leave_dock(dock_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # get the robot currently at this dock
    cursor.execute("SELECT robot_ip FROM Docks WHERE dock_id=(%s)", dock_id)
    if cursor.rowcount == 0:
        raise Exception("robot_leave_dock: No known dock #", dock_id)
    robot_ip = cursor.fetchone()[0]
    if robot_ip == "NULL":
        raise Exception("robot_leave_dock: No robot currently at dock #", dock_id)
    # release this robot from this dock
    cursor.execute("UPDATE Docks SET robot_ip=NULL WHERE robot_ip=(%s)", robot_ip)
    cursor.close()
    db.commit()
    db.close()
    return robot_ip


################################### ITEMS ####################################

def check_in_item(item_id, container_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # if the container has not been registered yet, log it
    cursor.execute("SELECT COUNT(*) FROM Containers WHERE container_id=(%s)", container_id)
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO Containers (container_id, status) VALUES (%s, 'TO_SHELF')", container_id)
    else:
        cursor.execute("UPDATE Containers SET status='TO_SHELF' WHERE container_id=(%s)", container_id)
    # insert the item-container info
    cursor.execute("INSERT INTO Items VALUES (%s, %s)", (item_id, container_id))
    # cleanup
    cursor.close()
    db.commit()
    db.close()

def check_out_item(item_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # figure out which container this item is in
    cursor.execute("SELECT container_id FROM Items WHERE item_id=(%s)", item_id)
    container_id = cursor.fetchone()[0]
    # check out this item
    cursor.execute("DELETE FROM Items WHERE item_id=%s", item_id)
    # if there's nothing left in the container, delete it from DB as well, and its responsible robot is free of container
    container_empty = False
    cursor.execute("SELECT COUNT(*) FROM Items WHERE container_id=(%s)", container_id)
    if cursor.fetchone()[0] == 0:
        cursor.execute("DELETE FROM Containers WHERE container_id=(%s)", container_id)
        cursor.execute("UPDATE Robots SET container_id=NULL WHERE container_id=(%s)", container_id)
        container_empty = True
    # otherwise, mark the container TO_SHELF, and it will be carried away by the same robot
    else:
        cursor.execute("UPDATE Containers SET status='TO_SHELF' WHERE container_id=(%s)", container_id)
    # cleanup
    cursor.close()
    db.commit()
    db.close()
    return container_empty

def locate_item(item_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # find which container this item is in
    cursor.execute("SELECT container_id FROM Items WHERE item_id=(%s)", item_id)
    if cursor.rowcount == 0:
        raise Exception("No item #" + str(item_id))
    container_id = cursor.fetchone()[0]
    # find the status and position of that container
    cursor.execute("SELECT * FROM Containers WHERE container_id=(%s)", container_id)
    if cursor.rowcount == 0:
        raise Exception("No container #" + str(container_id))
    result = cursor.fetchone()
    # cleanup
    cursor.close()
    db.commit()
    db.close()
    return result

################################### CONTAINERS ####################################

def update_container_pos(robot_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # get the container_id being carried and the robot's destination
    cursor.execute("SELECT container_id, dest_row, dest_col, dest_slot, dest_level FROM Robots WHERE robot_ip=(%s)", robot_ip)
    if cursor.rowcount == 0:
        raise Exception("update_container_pos: No container on robot ", robot_ip)
    (container_id, dest_row, dest_col, dest_slot, dest_level) = cursor.fetchone()
    # update the container's new position
    cursor.execute("UPDATE Containers SET status='ON_SHELF', row=(%s), col=(%s), slot=(%s), level=(%s) WHERE container_id=(%s)",
                   (dest_row, dest_col, dest_slot, dest_level, container_id))
    # clear the robot's container_id record
    cursor.execute("UPDATE Robots SET container_id=NULL where robot_ip=(%s)", robot_ip)
    # cleanup
    cursor.close()
    db.commit()
    db.close()

def update_container_dest(container_id, dest_row, dest_col, dest_slot, dest_level):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("UPDATE Containers SET status='TO_SHELF', row=(%s), col=(%s), slot=(%s), level=(%s) WHERE container_id=(%s)",
                   (dest_row, dest_col, dest_slot, dest_level, container_id))
    # cleanup
    cursor.close()
    db.commit()
    db.close()

# called when a robot fetch a container off shelf
# update the container's status
# return: the dock_id where the robot is assigned to head to
def container_off_shelf(robot_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # get the dock_id this robot is heading to
    cursor.execute("SELECT container_id, dest_dock_id FROM Robots WHERE robot_ip=(%s)", robot_ip)
    (container_id, dest_dock_id) = cursor.fetchone()
    # update the container's status
    container_new_status = ""
    if dest_dock_id <= LAST_IMPORT_DOCK:
        container_new_status = "TO_IMPORT"
    else:
        container_new_status = "TO_PACKING"
    cursor.execute("UPDATE Containers SET status=(%s) WHERE container_id=(%s)", (container_new_status, container_id))
    # cleanup
    cursor.close()
    db.commit()
    db.close()
    return dest_dock_id

def set_container_status(container_id, new_status):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("UPDATE Containers SET status=(%s) WHERE container_id=(%s)", (new_status, container_id))
    cursor.close()
    db.commit()
    db.close()

def get_container_carrier(container_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("SELECT container_id FROM Robots WHERE container_id=(%s)", container_id)
    if cursor.rowcount == 0:
        raise Exception("get_container_carrier: No requested container found")
    robot_ip = cursor.fetchone()[0]
    cursor.close()
    db.commit()
    db.close()
    return robot_ip

def get_container_info(container_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("SELECT * FROM Containers WHERE container_id=(%s)", container_id)
    if cursor.rowcount == 0:
        raise Exception("No container #" + str(container_id))
    result = cursor.fetchone()
    # cleanup
    cursor.close()
    db.commit()
    db.close()
    return result

def get_container_status(container_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("SELECT status FROM Containers WHERE container_id=(%s)", container_id)
    if cursor.rowcount == 0:
        raise Exception("No container #" + str(container_id))
    status = cursor.fetchone()[0]
    # cleanup
    cursor.close()
    db.commit()
    db.close()
    return status


################################### ROBOTS ####################################

def robot_join(robot_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    # if there's already one with this IP in DB, error
    cursor.execute("SELECT COUNT(*) FROM Robots WHERE robot_ip=(%s)", robot_ip)
    if cursor.fetchone()[0] != 0:
        raise Exception("Robot with same IP at work")
    else:
        cursor.execute("INSERT INTO Robots (robot_ip) VALUES (%s)", robot_ip)
    # cleanup
    cursor.close()
    db.commit()
    db.close()

def set_robot_dest_dock(robot_ip, dock_id):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("UPDATE Robots SET dest_dock_id=(%s) WHERE robot_ip=(%s)", (dock_id, robot_ip))
    cursor.close()
    db.commit()
    db.close()

def set_robot_dest_shelf(robot_ip, row, col, slot, level):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("UPDATE Robots SET dest_row=(%s), dest_col=(%s), dest_slot=(%s), dest_level=(%s) WHERE robot_ip=(%s)",
                   (row, col, slot, level, robot_ip))
    cursor.close()
    db.commit()
    db.close()

def get_container_on_robot(robot_ip):
    db = pymysql.connect(host=HOST, user=USER, db=DB)
    cursor = db.cursor()
    cursor.execute("SELECT container_id FROM Robots WHERE robot_ip=(%s)", robot_ip)
    if cursor.rowcount == 0:
        raise Exception("get_container_on_robot: No known robot ", robot_ip)
    container_id = cursor.fetchone()[0]
    if container_id == "NULL":
        raise Exception("get_container_on_robot: No container on robot ", robot_ip)
    # cleanup
    cursor.close()
    db.commit()
    db.close()
    return container_id
