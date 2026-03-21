import maya.cmds as cmds
import maya.mel as mel


def create_test_unknown_nodes_and_plugins():
    """
    Creates unknown nodes and plugins in Maya to test the CleanupScene extractor plugin.

    This script will:
    1. Create several unknown nodes (some locked, some unlocked)
    2. Create references to unknown plugins
    3. Print a summary of what was created for testing
    """

    print("=" * 60)
    print("CREATING TEST UNKNOWN NODES AND PLUGINS")
    print("=" * 60)

    # --- Create Unknown Nodes ---
    print("\n1. Creating unknown nodes...")

    unknown_nodes = []

    # Create some regular nodes first, then convert them to unknown type
    # This simulates what happens when plugins are unloaded

    # Method 1: Create nodes and use MEL to make them unknown
    test_nodes = []
    for i in range(5):
        # Create a simple transform node
        node_name = f"testUnknownNode_{i + 1}"
        node = cmds.createNode("transform", name=node_name)
        test_nodes.append(node)

    # Use MEL to convert some nodes to unknown type
    # This is a bit of a hack, but it simulates the real scenario
    for i, node in enumerate(test_nodes[:3]):
        try:
            # This MEL command can help create unknown nodes
            mel.eval(f'createNode "unknown" -n "{node}_unknown";')
            unknown_nodes.append(f"{node}_unknown")
            print(f"   Created unknown node: {node}_unknown")
        except Exception as e:
            print(f"   Failed to create unknown node {node}_unknown: {e}")

    # Method 2: Create unknown nodes directly (this might work in some Maya versions)
    for i in range(3, 6):
        try:
            unknown_node = cmds.createNode("unknown", name=f"directUnknown_{i}")
            unknown_nodes.append(unknown_node)
            print(f"   Created direct unknown node: directUnknown_{i}")
        except Exception as e:
            print(f"   Could not create direct unknown node: {e}")

    # Method 3: Alternative approach - create custom nodes that will become unknown
    for i in range(2):
        try:
            # Create a custom attribute that references a non-existent plugin
            node_name = f"customUnknown_{i + 1}"
            node = cmds.createNode("transform", name=node_name)
            # Add a custom attribute that would typically come from a plugin
            cmds.addAttr(node, longName="customPluginAttr", dataType="string")
            cmds.setAttr(f"{node}.customPluginAttr", "test_value", type="string")
            print(f"   Created node with custom attributes: {node_name}")
        except Exception as e:
            print(f"   Failed to create custom node: {e}")

    # --- Lock Some Unknown Nodes ---
    print("\n2. Locking some unknown nodes...")

    # Get all unknown nodes that actually exist
    actual_unknown_nodes = cmds.ls(type="unknown") or []

    if actual_unknown_nodes:
        # Lock every other unknown node
        for i, node in enumerate(actual_unknown_nodes):
            if i % 2 == 0:  # Lock every other node
                try:
                    cmds.lockNode(node, lock=True)
                    print(f"   Locked unknown node: {node}")
                except Exception as e:
                    print(f"   Failed to lock node {node}: {e}")
            else:
                print(f"   Left unlocked: {node}")
    else:
        print("   No unknown nodes found to lock")

    # --- Create Unknown Plugin References ---
    print("\n3. Creating unknown plugin references...")

    # The most reliable way to create unknown plugins is to:
    # 1. Load a plugin and create nodes that depend on it
    # 2. Unload the plugin, making it "unknown"

    created_plugins = []
    plugin_dependent_nodes = []

    # Method 1: Try with commonly available plugins
    test_plugins = [
        "matrixNodes",  # Usually available
        "quatNodes",  # Usually available
        "stereoCamera",  # Usually available
        "tiffFloatReader",  # Usually available
    ]

    for plugin_name in test_plugins:
        try:
            # Check if plugin exists but isn't loaded
            if not cmds.pluginInfo(plugin_name, query=True, loaded=True):
                # Load the plugin
                cmds.loadPlugin(plugin_name, quiet=True)
                print(f"   Loaded plugin: {plugin_name}")

                # Create a node that depends on this plugin (if possible)
                try:
                    if plugin_name == "matrixNodes":
                        node = cmds.createNode("decomposeMatrix", name=f"test_{plugin_name}_node")
                        plugin_dependent_nodes.append((node, plugin_name))
                        print(f"   Created node dependent on {plugin_name}: {node}")
                    elif plugin_name == "quatNodes":
                        node = cmds.createNode("eulerToQuat", name=f"test_{plugin_name}_node")
                        plugin_dependent_nodes.append((node, plugin_name))
                        print(f"   Created node dependent on {plugin_name}: {node}")
                    elif plugin_name == "stereoCamera":
                        node = cmds.createNode("stereoRigCamera", name=f"test_{plugin_name}_node")
                        plugin_dependent_nodes.append((node, plugin_name))
                        print(f"   Created node dependent on {plugin_name}: {node}")
                except Exception as node_error:
                    print(f"   Could not create node for {plugin_name}: {node_error}")

                # Now unload the plugin to make it "unknown"
                cmds.unloadPlugin(plugin_name, force=True)
                created_plugins.append(plugin_name)
                print(f"   Unloaded plugin: {plugin_name} (now should be unknown)")

        except Exception as e:
            print(f"   Could not work with plugin {plugin_name}: {e}")

    # Method 2: Create a temporary fake plugin reference using file I/O
    # This is more advanced but creates actual unknown plugin references
    try:
        import os
        import tempfile

        # Create a temporary .ma file with plugin requirements
        temp_ma_content = """//Maya ASCII 2023 scene
//Name: temp_scene_with_plugins.ma
//Last modified: Mon, Jan 01, 2024 12:00:00 PM
//Codeset: UTF-8
requires maya "2023";
requires "fakeTestPlugin.mll" "1.0";
requires "anotherFakePlugin.py" "2.0";
requires "missingPlugin.mll" "1.5";
createNode transform -n "temp_transform";
"""

        # Write temporary file
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "temp_unknown_plugins.ma")

        with open(temp_file, "w") as f:
            f.write(temp_ma_content)

        print(f"   Created temporary .ma file: {temp_file}")

        # Import the file (this should create unknown plugin references)
        try:
            cmds.file(temp_file, i=True, namespace="unknownPluginTest")
            print("   Imported file with unknown plugin requirements")
        except Exception as import_error:
            print(f"   Import created unknown plugins (expected): {import_error}")

        # Clean up temp file
        try:
            os.remove(temp_file)
            print("   Cleaned up temporary file")
        except:
            pass

    except Exception as e:
        print(f"   Could not create temporary plugin references: {e}")

    # Method 3: Use Maya's internal plugin system more directly
    try:
        # This uses Maya's internal mechanism to add plugin requirements
        fake_plugins = ["testUnknownPlugin.mll", "fakePlugin123.py"]

        for fake_plugin in fake_plugins:
            try:
                # This MEL approach sometimes works to add plugin dependencies
                mel.eval(f'addToPluginPath ""; pluginInfo -edit -command "fakecmd" "{fake_plugin}";')
                print(f"   Added fake plugin reference: {fake_plugin}")
            except:
                # Try alternative MEL approach
                try:
                    mel.eval(f'unknownPlugin -dataType "fakeType" "{fake_plugin}";')
                    print(f"   Added unknown plugin via dataType: {fake_plugin}")
                except Exception as mel_error:
                    print(f"   Could not add {fake_plugin}: {mel_error}")

    except Exception as e:
        print(f"   Advanced plugin creation failed: {e}")

    print(f"\n   Summary: Attempted to create unknown plugins using {len(test_plugins)} methods")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("TEST SETUP COMPLETE")
    print("=" * 60)

    # Check what we actually created
    final_unknown_nodes = cmds.ls(type="unknown") or []
    final_unknown_plugins = cmds.unknownPlugin(query=True, list=True) or []

    print(f"\nFinal unknown nodes in scene: {len(final_unknown_nodes)}")
    for node in final_unknown_nodes:
        is_locked = cmds.lockNode(node, query=True)[0] if cmds.objExists(node) else False
        lock_status = "LOCKED" if is_locked else "unlocked"
        print(f"   - {node} ({lock_status})")

    print(f"\nFinal unknown plugins in scene: {len(final_unknown_plugins)}")
    for plugin in final_unknown_plugins:
        print(f"   - {plugin}")

    print(f"\nTotal test nodes created: {len(test_nodes)}")
    print(f"Plugin-dependent nodes: {len(plugin_dependent_nodes)}")

    print("\n" + "=" * 60)
    print("You can now run your CleanupScene extractor plugin to test it!")
    print("The plugin should remove all unknown nodes and plugins.")
    print("=" * 60)


def cleanup_scene():
    """
    Deletes all unknown nodes (including locked ones) and removes all
    unknown plugins from the scene. It also cleans up any remaining
    test nodes created by the setup script.
    """
    print("\n" + "=" * 60)
    print("CLEANING UP SCENE")
    print("=" * 60)

    # --- Step 1: Find and delete all unknown nodes ---
    print("\n1. Deleting unknown nodes...")
    unknown_nodes = cmds.ls(type="unknown") or []

    if not unknown_nodes:
        print("   No unknown nodes found to delete.")
    else:
        print(f"   Found {len(unknown_nodes)} unknown nodes.")
        unlocked_count = 0

        # Unlock all nodes first before attempting to delete
        for node in unknown_nodes:
            try:
                if cmds.lockNode(node, query=True)[0]:
                    cmds.lockNode(node, lock=False)
                    print(f"   Unlocked node: {node}")
                    unlocked_count += 1
            except Exception as e:
                # This might happen if the node is part of a locked, referenced file
                print(f"   Could not unlock node {node}. It may be part of a reference. Warning: {e}")

        # Now, delete all the identified unknown nodes
        try:
            print(f"\n   Attempting to delete {len(unknown_nodes)} unknown nodes...")
            cmds.delete(unknown_nodes)
            print("   Successfully deleted the unknown nodes.")
        except Exception as e:
            print(f"   An error occurred during deletion of unknown nodes: {e}")

    # --- Step 2: Find and remove all unknown plugins ---
    print("\n2. Removing unknown plugins...")
    unknown_plugins = cmds.unknownPlugin(query=True, list=True) or []

    if not unknown_plugins:
        print("   No unknown plugins found to remove.")
    else:
        print(f"   Found {len(unknown_plugins)} unknown plugins: {', '.join(unknown_plugins)}")
        removed_count = 0
        for plugin in unknown_plugins:
            try:
                cmds.unknownPlugin(plugin, remove=True)
                print(f"   Removed unknown plugin: {plugin}")
                removed_count += 1
            except Exception as e:
                print(f"   Failed to remove unknown plugin {plugin}: {e}")
        print(f"\n   Successfully removed {removed_count} unknown plugins.")

    # --- Step 3: Clean up any remaining test transform nodes ---
    print("\n3. Cleaning up leftover test nodes...")
    test_transforms = (
        cmds.ls(
            "testUnknownNode_*",
            "directUnknown_*",
            "customUnknown_*",
            "test_*_node",
            "unknownPluginTest:*",
            type="transform",
        )
        or []
    )
    if test_transforms:
        try:
            cmds.delete(test_transforms)
            print(f"   Deleted {len(test_transforms)} leftover test transform nodes.")
        except Exception as e:
            print(f"   Could not delete all leftover test nodes: {e}")
    else:
        print("   No leftover test transform nodes found.")

    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)


# Run the test setup
create_test_unknown_nodes_and_plugins()

# Uncomment the line below if you want to clean up afterwards
cleanup_scene()
