CREATE DATABASE IF NOT EXISTS robot_admin
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE robot_admin;

-- 명령 전체 흐름 로그
CREATE TABLE IF NOT EXISTS command_logs (
    command_id   VARCHAR(100) PRIMARY KEY,
    raw_text     TEXT,
    parsed_text  JSON,
    status       VARCHAR(50),
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at  DATETIME
);

-- 노드 로그 수집 (WARN 이상)
CREATE TABLE IF NOT EXISTS error_logs (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    command_id VARCHAR(100),
    level      VARCHAR(10),
    node_name  VARCHAR(100),
    message    TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 상태 변화 로그
CREATE TABLE IF NOT EXISTS state_logs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    command_id       VARCHAR(100),
    state            VARCHAR(50),
    detail           TEXT,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 액션 단위 실행 로그
CREATE TABLE IF NOT EXISTS action_logs (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    command_id VARCHAR(100),
    seq        INT,
    action     VARCHAR(100),
    params     JSON,
    status     VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Object Detection 결과 로그
CREATE TABLE IF NOT EXISTS detection_logs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    command_id       VARCHAR(100),
    object_name      VARCHAR(100),
    confidence       FLOAT,
    position_x       FLOAT,
    position_y       FLOAT,
    position_z       FLOAT,
    detected         BOOLEAN,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
