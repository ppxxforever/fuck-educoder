CREATE DATABASE IF NOT EXISTS `finance1`;
use finance1;
DELETE FROM client WHERE c_id NOT IN (SELECT b_c_id FROM bank_card);