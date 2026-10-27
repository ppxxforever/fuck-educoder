CREATE DATABASE IF NOT EXISTS `MyDb`;
USE MyDb;

DROP TABLE IF EXISTS `hr`;
CREATE TABLE hr(
    id char(10) PRIMARY KEY,
    name varchar(32) NOT NULL,
    mz char(16) DEFAULT '汉族'
);
