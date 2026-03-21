import maya.cmds as cmds


def query_selected_attribute(attribute_name):
    """
    Queries a specified attribute on the selected object.
    It first checks the selected node itself (e.g., transform, group).
    If not found and the selected node is a transform with shape(s),
    it then checks the shape node(s).

    Args:
        attribute_name (str): The name of the attribute to query.

    Returns:
        The attribute value if found, otherwise None.
    """
    # Get the current selection. ls() without type filter is more general.
    selection = cmds.ls(selection=True, long=True)  # Use long names for clarity

    if not selection:
        cmds.warning("No object selected. Please select an object.")
        return None

    # We'll operate on the first selected object
    selected_node = selection[0]
    node_name_for_messages = selected_node.split("|")[-1]  # Get short name for messages

    # --- Attempt 1: Check the selected node directly ---
    # This handles attributes on transforms, groups, or even directly selected shapes.
    if cmds.attributeQuery(attribute_name, node=selected_node, exists=True):
        try:
            attribute_value = cmds.getAttr(selected_node + "." + attribute_name)
            print(
                f"Object: '{node_name_for_messages}', Node Type: '{cmds.nodeType(selected_node)}', Attribute: '{attribute_name}', Value: {attribute_value}"
            )
            return attribute_value
        except Exception as e:
            # Log error but continue to check shape if applicable
            cmds.warning(
                f"Error getting attribute '{attribute_name}' directly from selected node '{node_name_for_messages}': {e}"
            )
            # Fall through to check shape nodes if this was a transform

    # --- Attempt 2: If selected node is a transform, check its shape(s) ---
    # (Relevant if the attribute wasn't found on the transform itself)
    # We check nodeType to ensure listRelatives -s makes sense.
    is_transform = "transform" in cmds.nodeType(selected_node, inherited=True)

    if is_transform:
        # List all shape nodes under the transform
        shapes = cmds.listRelatives(selected_node, shapes=True, fullPath=True, noIntermediate=True)
        if shapes:
            print(shapes)
            for shape_node in shapes:
                shape_name_for_messages = shape_node.split("|")[-1]
                if cmds.attributeQuery(attribute_name, node=shape_node, exists=True):
                    try:
                        attribute_value = cmds.getAttr(shape_node + "." + attribute_name)
                        print(
                            f"Object: '{node_name_for_messages}', Found on Shape: '{shape_name_for_messages}', Node Type: '{cmds.nodeType(shape_node)}', Attribute: '{attribute_name}', Value: {attribute_value}"
                        )
                        return attribute_value  # Return value from the first shape that has it
                    except Exception as e:
                        cmds.warning(
                            f"Error getting attribute '{attribute_name}' from shape node '{shape_name_for_messages}' (of selected '{node_name_for_messages}'): {e}"
                        )
                        # Continue to check other shapes if any

    # If attribute was not found on the selected node or its shapes
    cmds.warning(
        f"Attribute '{attribute_name}' not found on selected object '{node_name_for_messages}' or its relevant shape nodes."
    )
    return None


attribute_to_query = "rdo_div"

print("--- Running Attribute Query ---")
print(f"Querying attribute: '{attribute_to_query}'")
queried_value = query_selected_attribute(attribute_to_query)

if queried_value is not None:
    print(f"Query executed. Value found: {queried_value}")
else:
    print("Query executed. Could not retrieve attribute value or an error occurred (see warnings above).")
