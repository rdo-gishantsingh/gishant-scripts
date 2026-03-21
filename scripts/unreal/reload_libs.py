import importlib

# List all the specific modules you want to reload
modules_to_reload = [
    "rdo_unreal.api",
    "rdo_unreal.api.logger",
    "rdo_unreal.api.report_builder",
    "rdo_unreal.plugins.rig_switcher.rig_switcher",
    "rdo_unreal.plugins.rig_switcher",
    "rdo_unreal.plugins.texture_update",
    "rdo_unreal.plugins.shader_hook_up",
    "rdo_unreal.plugins.material_to_instance",
    "rdo_unreal.plugins.material_to_instance.converter",
    "rdo_unreal.plugins.material_to_instance.widget",
]

print("--- Starting module reload ---")
for module_name in modules_to_reload:
    try:
        # Dynamically import the module using its string name
        module = importlib.import_module(module_name)
        # Reload the imported module
        importlib.reload(module)
        print(f"✅ Reloaded: {module_name}")
    except ImportError as e:
        print(f"❌ Failed to reload {module_name}: {e}")
print("--- Reload complete ---")
