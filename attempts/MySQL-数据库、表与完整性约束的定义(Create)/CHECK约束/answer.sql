CREATE DATABASE IF NOT EXISTS `MyDb`;
USE MyDb;
DROP TABLE IF EXISTS `products`;
CREATE TABLE products(
    pid char(10) PRIMARY KEY,
    name varchar(32),
    brand char(10),
    price int,
    CONSTRAINT CK_products_brand CHECK (brand in ('A','B')),
    CONSTRAINT CK_products_price CHECK (price > 0)
);
