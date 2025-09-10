import maya.cmds as cmds


def rename_hierarchy_nodes(root_node="adam_rig", old_string="adam", new_string="chartestrig"):
    """
    Recursively renames nodes in a hierarchy, replacing occurrences of old_string
    with new_string while maintaining namespace structure.

    Example: 'adam_modelHair_01_:fronthair_cards_GEO' becomes 'chartestrig_modelHair_01_:fronthair_cards_GEO'

    Args:
        root_node (str): The root node to start renaming from
        old_string (str): The string to replace in node names
        new_string (str): The replacement string
    """
    # If exact root doesn't exist, try to find a top-level candidate
    if not cmds.objExists(root_node):
        assemblies = cmds.ls(assemblies=True, long=True) or []
        variants = {
            root_node,
            root_node.replace(old_string, new_string),
        }
        candidate = next((a for a in assemblies if a.split("|")[-1] in variants), None)
        if candidate:
            root_node = candidate
            print("Using root node: '{}'".format(root_node))
        else:
            cmds.warning("Root node '{}' not found. Aborting script.".format(root_node))
            return

    # Get all descendants in the hierarchy
    all_descendants = cmds.ls(root_node, dag=True, long=True) or []

    # First, collect all unique namespaces that need renaming
    namespaces_to_rename = set()
    for node_path in all_descendants:
        short_name = node_path.split("|")[-1]
        if ":" in short_name:
            namespace_part = ":".join(short_name.split(":")[:-1])
            if old_string in namespace_part:
                namespaces_to_rename.add(namespace_part)

    # Rename namespaces first
    for namespace in namespaces_to_rename:
        new_namespace = namespace.replace(old_string, new_string)
        try:
            if cmds.namespace(exists=namespace):
                cmds.namespace(rename=[namespace, new_namespace])
                print("Renamed namespace '{}' -> '{}'".format(namespace, new_namespace))
        except Exception as e:
            cmds.warning("Could not rename namespace '{}'. Error: {}".format(namespace, e))

    # Then handle non-namespaced nodes
    all_descendants = cmds.ls(root_node, dag=True, long=True) or []  # Refresh the list
    for node_path in reversed(all_descendants):
        try:
            short_name = node_path.split("|")[-1]

            # Only process non-namespaced nodes or nodes where the node name itself needs renaming
            if ":" not in short_name:
                # Non-namespaced node
                final_name = short_name.replace(old_string, new_string)
            else:
                # Namespaced node - only rename if the node name part (after colon) contains old_string
                namespace_part = ":".join(short_name.split(":")[:-1])
                node_name = short_name.split(":")[-1]
                if old_string in node_name:
                    new_node_name = node_name.replace(old_string, new_string)
                    final_name = namespace_part + ":" + new_node_name
                else:
                    continue  # Skip if no change needed

            # Only rename if the name actually changes
            if final_name != short_name:
                cmds.rename(node_path, final_name)
                print("Renamed '{}' -> '{}'".format(short_name, final_name))

        except Exception as e:
            cmds.warning("Could not rename node '{}'. Error: {}".format(node_path, e))

    print("\nHierarchy renaming complete for: '{}'".format(root_node))


# --- How to run the script ---
# To execute the function, run the following line in the Maya Script Editor:
#
rename_hierarchy_nodes()
#
# Or with custom parameters:
# rename_hierarchy_nodes(root_node='your_root_object', old_string='old_name', new_string='new_name')
