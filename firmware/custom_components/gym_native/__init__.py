import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID
from esphome.components import esp32, light, time, lvgl
from esphome.components.lvgl import defines

DEPENDENCIES = ['wifi', 'lvgl', 'light', 'time', 'web_server']
AUTO_LOAD = ['json']
ns = cg.esphome_ns.namespace('gym_native')
GymNative = ns.class_('GymNative', cg.Component)

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(GymNative),
    cv.Required('url'): cv.url,
    cv.Required('token'): cv.string_strict,
    cv.Required('write_token'): cv.string_strict,
    cv.Optional('timezone', default='Europe/Oslo'): cv.string_strict,
    cv.Optional('language', default='nb'): cv.one_of('nb', 'en'),
    cv.Required('backlight'): cv.use_id(light.LightState),
    cv.Required('clock'): cv.use_id(time.RealTimeClock),
    cv.Required('display_lvgl'): cv.use_id(lvgl.LvglComponent),
}).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    esp32.include_builtin_idf_component('esp_http_client')
    for widget in ['LABEL', 'BUTTON', 'IMAGE']:
        defines.add_define('LV_USE_' + widget, '1')
    # LVGL 9.5's RGB565 scaling path is conditional on BOTH RGB565 and
    # RGB565A8, even when the source image itself is opaque RGB565.
    defines.add_define('LV_DRAW_SW_SUPPORT_RGB565A8', '1')
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_url(config['url']))
    cg.add(var.set_token(config['token']))
    cg.add(var.set_write_token(config['write_token']))
    cg.add(var.set_timezone(config['timezone']))
    cg.add(var.set_language(config['language']))

    for key in ['backlight', 'clock', 'display_lvgl']:
        target = await cg.get_variable(config[key])
        cg.add(getattr(var, 'set_' + key)(target))
