// Prevents an extra console window on Windows (harmless on macOS).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    meeting_processor_desktop_lib::run();
}
