CREATE DATABASE IF NOT EXISTS `MyDb`;
USE `MyDb`;

ALTER TABLE `orderDetail` DROP COLUMN `orderDate`;
ALTER TABLE `orderDetail` ADD COLUMN `unitPrice` decimal(10,2);