CREATE DATABASE IF NOT EXISTS `finance1`;
use finance1;

UPDATE property
SET pro_id_card = (
    SELECT c_id_card
    FROM client
    WHERE client.c_id = property.pro_c_id
);

/* the end of your code */