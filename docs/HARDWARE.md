# Supported hardware

The only supported production target is the **Guition JC8012P4A1 v3** with
ESP32-P4 production silicon, C6 SDIO Wi-Fi, GSL3680 touch and an 800×1280 display
rotated into 1280×800 landscape.

`firmware/hardware/jc8012p4a1-v3.yaml` pins ESP-IDF 5.5.5, the v3 display
initialisation, 40 MHz SDIO, 70 MHz/840 Mbps display timing and the existing
16 MB partition offsets. Local MIPI/GSL components are copied from EspControl
v2.13.0 commit `9bf8567f1272b0b2bbe7788de95e8772620561bf`, with hashes in
`firmware/custom_components_v3/upstream.json` and original notices intact.

The PHY-clock patch is intentional. Do not substitute an original/v2 board
profile based only on a seller's model name. Identify the PCB revision, preserve
the manufacturer's firmware/configuration and have a working USB recovery path.
Partition changes may require USB even when ordinary firmware updates use OTA.

References:

- [EspControl v3 hardware profile](https://github.com/jtenniswood/espcontrol/blob/v2.13.0/devices/guition-esp32-p4-jc8012p4a1-v3/device/device.yaml)
- [EspControl v3 installation/recovery](https://jtenniswood.github.io/espcontrol/screens/jc8012p4a1-v3)
- [Local driver provenance](../firmware/custom_components_v3/upstream.json)

Tests verify source/geometry and compilation; they cannot prove your panel's
physical LCD, touch calibration or board revision. Validate those yourself before
logging a session. Other board variants remain unsupported, not implicitly safe.
