CREATE TABLE Containers (
    container_id TINYINT(3) UNSIGNED PRIMARY KEY, 
    x TINYINT(3) UNSIGNED, 
    y TINYINT(3) UNSIGNED, 
    slot TINYINT(3) UNSIGNED, 
    level TINYINT(3) UNSIGNED, 
    status ENUM("TO_SHELF", "ON_SHELF", "RESERVED", "TO_PACKING", "TO_IMPORT") NOT NULL
);

CREATE TABLE Items (
    item_id TINYINT(3) UNSIGNED PRIMARY KEY, 
    container_id TINYINT(3) UNSIGNED NOT NULL, 
    FOREIGN KEY (container_id) REFERENCES Containers(container_id)
);

CREATE TABLE Docks (
    dock_id TINYINT(3) UNSIGNED PRIMARY KEY, 
    dock_type ENUM("PACKING", "IMPORT") NOT NULL, 
    worker_ip VARCHAR(20) UNIQUE NOT NULL, 
    robot_ip VARCHAR(20) UNIQUE DEFAULT NULL, -- the robot now at this dock
    grasper_position ENUM("LEFT", "RIGHT")
);

CREATE TABLE Robots (
    robot_ip VARCHAR(20) PRIMARY KEY, 
    container_id TINYINT(3) UNSIGNED UNIQUE, -- the container it carries or is going to carry, NULL if none
    dest_dock_id TINYINT(3) UNSIGNED, 
    dest_x TINYINT(3) UNSIGNED, 
    dest_y TINYINT(3) UNSIGNED, 
    dest_slot TINYINT(3) UNSIGNED, 
    dest_level TINYINT(3) UNSIGNED, 
    FOREIGN KEY (container_id) REFERENCES Containers(container_id)
        ON DELETE SET NULL, 
    FOREIGN KEY (dest_dock_id) REFERENCES Docks(dock_id)
        ON DELETE SET NULL
);