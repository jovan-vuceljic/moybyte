// moy_leds's MicroPython binding: the `leds` device API's driver (moy_leds.h)
// as the module `moy_leds`, its names those face.json lists, every row
// generated into modmoy_leds_face.h. A refusal is a negative errno, which the
// Python face (runtime/system/dev_leds.py) raises.

#include "py/runtime.h"

#include "moy_leds.h"

#include "modmoy_leds_face.h"

static const mp_rom_map_elem_t leds_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_moy_leds) },
    MOY_FACE_MOY_LEDS_ROWS
};
static MP_DEFINE_CONST_DICT(leds_globals, leds_globals_table);

const mp_obj_module_t moy_leds_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&leds_globals,
};

MP_REGISTER_MODULE(MP_QSTR_moy_leds, moy_leds_module);
