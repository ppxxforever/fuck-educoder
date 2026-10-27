CREATE DATABASE IF NOT EXISTS `finance1`;
use finance1;
INSERT INTO client (c_id, c_name, c_mail, c_id_card, c_phone)
SELECT c_id, c_name, c_mail, c_id_card, c_phone
FROM new_client;