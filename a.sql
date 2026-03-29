CREATE DATABASE inventory_db;
USE inventory_db;

CREATE TABLE product (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) UNIQUE,
    price FLOAT,
    qty INT,
    reorder_level INT
);

CREATE TABLE bill (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME,
    total_amount FLOAT
);

CREATE TABLE bill_item (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bill_id INT,
    product_name VARCHAR(120),
    qty INT,
    price FLOAT
);