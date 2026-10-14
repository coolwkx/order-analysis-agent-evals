-- Run once using a database administrator. Do not rerun INSERT blindly.
CREATE DATABASE IF NOT EXISTS agent_eval_lab CHARACTER SET utf8mb4;
USE agent_eval_lab;
CREATE TABLE IF NOT EXISTS orders (
    order_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_created_at (created_at)
);
INSERT INTO orders (order_id, user_id, amount, created_at) VALUES
    (1,101,100.00,'2026-09-01 00:00:00'),
    (2,101,200.00,'2026-09-15 12:00:00'),
    (3,102,80.00,'2026-09-30 23:59:59'),
    (4,102,999.00,'2026-10-01 00:00:00'),
    (5,103,50.00,'2026-08-31 23:59:59');
-- Create agent_reader separately with your own password, then run:
-- GRANT SELECT ON agent_eval_lab.orders TO 'agent_reader'@'localhost';
