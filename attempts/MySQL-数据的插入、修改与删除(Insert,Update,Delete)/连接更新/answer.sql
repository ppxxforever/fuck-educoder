CREATE DATABASE IF NOT EXISTS `finance1`;
use finance1;

update property p
join client c on p.pro_c_id = c.c_id
set p.pro_id_card = c.c_id_card;

/* the end of your code */
