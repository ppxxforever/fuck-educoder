CREATE DATABASE IF NOT EXISTS `finance1`;
use finance1;
INSERT INTO client
SELECT * FROM new_client;