// moy_lcd: what the SPI panel module (modmoy_lcd.c) offers other C.
//
// moy_lcd_card_gate(on): the panel's gate around one card transfer, where the
// card's MISO is the panel's D/C pad (MOY_LCD_DC_IS_MISO, the CoreS3's): on,
// the feeder drained and the pad turned to the card; off, given back. It is
// counted, so a volume op that holds the store's gate already nests. Defined
// only on such a board; native/moy_sd names it weak.

#ifndef MOY_LCD_H
#define MOY_LCD_H

void moy_lcd_card_gate(int on);

#endif // MOY_LCD_H
