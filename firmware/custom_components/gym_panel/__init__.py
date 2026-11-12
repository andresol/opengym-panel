import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID
from esphome.components import esp32
DEPENDENCIES = ['wifi', 'lvgl']
AUTO_LOAD = ['json']
ns = cg.esphome_ns.namespace('gym_panel')
GymPanel = ns.class_('GymPanel', cg.Component)
CONFIG_SCHEMA = cv.Schema({cv.GenerateID(): cv.declare_id(GymPanel), cv.Required('url'): cv.url, cv.Required('token'): cv.string_strict}).extend(cv.COMPONENT_SCHEMA)
async def to_code(config):
    esp32.include_builtin_idf_component("esp_http_client")
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_url(config['url']))
    cg.add(var.set_token(config['token']))
