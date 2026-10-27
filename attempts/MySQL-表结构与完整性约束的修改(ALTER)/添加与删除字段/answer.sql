CREATE DATABASE IF NOT EXISTS `MyDb`;
use MyDb;

ALTER TABLE orderdetail DROP COLUMN orderDate;
ALTER TABLE orderdetail ADD COLUMN unitPrice decimal(10,2);